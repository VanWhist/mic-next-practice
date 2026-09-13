"""MIC 次の練習 — Playwright検証（幅430px、APIはすべてモック）

実行: python tests/test_app.py [スクリーンショットの保存先]
外部への通信はすべて page.route で差し止め、モックで返す。
"""
import json
import sys
import threading
from datetime import date, timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SHOT_DIR = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests" / "screenshots"
ATHLETE = "a0000test"
TODAY = date.today()


def d(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


AIRLOG = {
    "athletes": [{"id": ATHLETE, "name": "テスト選手", "createdAt": ""}, {"id": "aother", "name": "別の選手", "createdAt": ""}],
    "records": [
        {"id": "r1", "athlete": ATHLETE, "category": "water", "date": d(-3), "rows": [
            {"trickId": "inv_bf", "success": 3, "fail": 2}, {"trickId": "rot_7", "success": 4, "fail": 0}]},
        {"id": "r2", "athlete": ATHLETE, "category": "water", "date": d(-10), "rows": [
            {"trickId": "up_daffy", "success": 5, "fail": 0}, {"trickId": "airtime", "success": 1, "fail": 0}]},
        {"id": "r3", "athlete": ATHLETE, "category": "trampoline", "date": d(-1), "rows": [{"trickId": "inv_btf", "reps": 3}]},
        {"id": "r4", "athlete": "aother", "category": "water", "date": d(-2), "rows": [{"trickId": "oax_14", "success": 1, "fail": 0}]},
    ],
    "videos": [], "coachNotes": [], "version": 1,
}

EVENTS = [
    {"eventId": "e_past", "date": d(-3), "kubun": "午前", "place": "さのさか", "note": ""},
    {"eventId": "e1", "date": d(1), "kubun": "午前", "place": "さのさか", "note": "板を持参"},
    {"eventId": "e2", "date": d(1), "kubun": "午後", "place": "さのさか", "note": ""},
    {"eventId": "e3", "date": d(5), "kubun": "終日", "place": "WJM", "note": ""},
]


class MockBackend:
    def __init__(self, events):
        self.events = events
        self.plans = []
        self.posts = []

    def handle(self, route):
        url = route.request.url
        if "AKfycbxbFOiI0" in url:
            if route.request.method == "POST":
                body = json.loads(route.request.post_data)
                self.posts.append(body)
                plan = {"planId": "p%d" % len(self.posts), "athleteId": body["athleteId"], "eventId": body["eventId"],
                        "improve": body["improve"], "check": body["check"], "createdAt": "", "status": "有効"}
                self.plans = [p for p in self.plans if p["eventId"] != plan["eventId"]] + [plan]
                return self.fulfill(route, {"ok": True, "plan": plan})
            return self.fulfill(route, {"ok": True, "events": self.events, "plans": self.plans})
        if "AKfycbyH7nX" in url:
            return self.fulfill(route, AIRLOG)
        if "AKfycbwhxPSd" in url:
            return self.fulfill(route, {"records": []})
        if url.startswith("http://127.0.0.1"):
            return route.continue_()
        return route.abort()

    @staticmethod
    def fulfill(route, obj):
        route.fulfill(status=200, content_type="application/json", headers={"Access-Control-Allow-Origin": "*"},
                      body=json.dumps(obj, ensure_ascii=False))


def start_server():
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *a, **k: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok), detail))
    print(("OK   " if ok else "FAIL ") + name + (("  — " + detail) if detail else ""))


def open_page(browser, base, backend, query):
    page = browser.new_page(viewport={"width": 430, "height": 932})
    errors = []
    page.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
    page.on("console", lambda m: errors.append("console.error: " + m.text) if m.type == "error" else None)
    page.route("**/*", backend.handle)
    page.goto(base + "/index.html" + query)
    return page, errors


def main():
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    server = start_server()
    base = "http://127.0.0.1:%d" % server.server_address[1]
    all_errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # 1. 練習日が0件
        page, errors = open_page(browser, base, MockBackend([]), "?a=" + ATHLETE)
        page.wait_for_selector("[data-testid=no-events]")
        check("0件: 空の案内が出る", page.is_visible("[data-testid=no-events]"))
        check("0件: 「あと0日」を出さない", page.locator("[data-testid=hero]").count() == 0)
        check("0件: 決めるボタンが出ない", page.locator("[data-testid=next-cta]").count() == 0)
        page.screenshot(path=str(SHOT_DIR / "01_no_events.png"), full_page=True)
        all_errors += errors
        page.close()

        # 2. 通常（練習日あり）
        backend = MockBackend(EVENTS)
        page, errors = open_page(browser, base, backend, "?a=" + ATHLETE)
        page.wait_for_selector("[data-testid=hero]")
        page.wait_for_function("document.body.innerText.includes('テスト選手')")
        hero = page.inner_text("[data-testid=hero]")
        check("トップ: 残りの練習日は日付の数で2日（午前/午後は1日）", "あと\n2日" in hero or "あと2日" in hero.replace("\n", ""), hero.replace("\n", " "))
        check("トップ: これからの練習日が3件", page.locator("[data-testid=event-row]").count() == 3)
        check("トップ: 3件目は決められない（次の2回分だけ）", page.locator("button[data-testid=event-row]").count() == 2)
        past_text = page.inner_text("[data-testid=past-row]")
        check("トップ: 過去の練習日にエアlogの実績が並ぶ", "バックフル 5本" in past_text and "720 4本" in past_text, past_text.replace("\n", " "))
        banned = ["達成", "未達", "ノルマ", "残り本数", "あと何本"]
        body = page.inner_text("body")
        check("トップ: 達成・未達・本数ノルマの語が出ない", not any(w in body for w in banned))
        page.screenshot(path=str(SHOT_DIR / "02_top.png"), full_page=True)

        page.click("[data-testid=next-cta]")
        page.wait_for_selector("text=次の練習で、いちばん良くしたいことは？")
        keys = page.eval_on_selector_all("[data-testid=choice]", "els => els.map(e => e.dataset.key)")
        check("選択肢: 最近のWJの技が新しい順（トランポリン・他選手・10本ジャンプは除く）",
              keys[:3] == ["inv_bf", "rot_7", "up_daffy"], str(keys))
        check("選択肢: コーチと相談したい／自分で書く がある", "__consult__" in keys and "__free__" in keys)
        sizes = page.eval_on_selector_all("[data-testid=choice]", "els => els.map(e => [Math.round(e.getBoundingClientRect().width), Math.round(e.getBoundingClientRect().height)])")
        consult_size = sizes[keys.index("__consult__")]
        trick_size = sizes[keys.index("inv_bf")]
        check("選択肢: コーチと相談したいは技と同じ大きさ", consult_size == trick_size, "consult=%s trick=%s" % (consult_size, trick_size))

        # 3. 自分で書く を空のまま進む／保存しようとする
        page.click("[data-key=__free__]")
        page.click("[data-testid=next-btn]")
        check("自分で書く(良くしたいこと)が空: 進まずに案内が出る",
              page.is_visible("[data-testid=error]") and page.is_visible("text=次の練習で、いちばん良くしたいことは？"),
              page.inner_text("[data-testid=error]") if page.is_visible("[data-testid=error]") else "")
        page.fill("#improve-text", "   ")
        page.click("[data-testid=next-btn]")
        check("自分で書く(良くしたいこと)が空白だけ: 進まない", page.is_visible("[data-testid=error]"))
        page.screenshot(path=str(SHOT_DIR / "03_free_empty_improve.png"), full_page=True)
        page.fill("#improve-text", "踏切で上体を起こす")
        page.click("[data-testid=next-btn]")
        page.wait_for_selector("text=それができたと、何を見て分かる？")
        page.click("[data-key=__free__]")
        page.click("[data-testid=save-btn]")
        check("自分で書く(確かめること)が空で保存: 保存されず案内が出る",
              page.is_visible("[data-testid=error]") and len(backend.posts) == 0,
              page.inner_text("[data-testid=error]") + " / posts=%d" % len(backend.posts))
        page.screenshot(path=str(SHOT_DIR / "04_free_empty_check.png"), full_page=True)

        # 4. 戻って「コーチと相談したい」を選ぶ
        page.click("text=‹ 戻る")
        page.click("[data-key=__consult__]")
        page.screenshot(path=str(SHOT_DIR / "05_consult_selected.png"), full_page=True)
        page.click("[data-testid=next-btn]")
        page.wait_for_selector("text=それができたと、何を見て分かる？")
        check_keys = page.eval_on_selector_all("[data-testid=choice]", "els => els.map(e => e.dataset.key)")
        check("相談: 確かめることに例4つ＋コーチと決める＋自分で書く",
              check_keys == ["成功する本数が増える", "踏切のタイミングが合う", "着地が安定する", "コーチにOKと言われる", "練習でコーチと決める", "__free__"], str(check_keys))
        check("相談: 失敗扱いの文言が出ない", not any(w in page.inner_text("body") for w in ["自分で決められ", "失敗", "未達"]))
        page.click("[data-key=練習でコーチと決める]")
        page.screenshot(path=str(SHOT_DIR / "06_consult_check.png"), full_page=True)
        page.click("[data-testid=save-btn]")
        page.wait_for_selector("[data-testid=next-plan]")
        check("相談: 保存内容", backend.posts[-1] == {"type": "savePlan", "athleteId": ATHLETE, "eventId": "e1", "improve": "コーチと相談したい", "check": "練習でコーチと決める"}, json.dumps(backend.posts[-1], ensure_ascii=False))

        # 5. 保存後のトップ
        plan_text = page.inner_text("[data-testid=next-plan]")
        check("保存後トップ: 次の練習／確かめること が出る", "次の練習コーチと相談したい" in plan_text.replace("\n", "") and "確かめること練習でコーチと決める" in plan_text.replace("\n", ""), plan_text.replace("\n", " / "))
        check("保存後トップ: 保存しましたが出る", page.is_visible("[data-testid=flash]"))
        page.screenshot(path=str(SHOT_DIR / "07_after_save_consult.png"), full_page=True)

        # 6. 作り直す（技＋例）→ 置き換わる（繰り越さない）
        page.click("text=作り直す >> nth=0")
        page.click("[data-key=inv_bf]")
        page.click("[data-testid=next-btn]")
        page.click("[data-key=着地が安定する]")
        page.click("[data-testid=save-btn]")
        page.wait_for_selector("[data-testid=next-plan]")
        plan_text = page.inner_text("[data-testid=next-plan]").replace("\n", "")
        check("作り直し: 新しい目標に置き換わる", "次の練習バックフル" in plan_text and "確かめること着地が安定する" in plan_text and "相談" not in plan_text, plan_text)
        page.reload()
        page.wait_for_selector("[data-testid=next-plan]")
        plan_text = page.inner_text("[data-testid=next-plan]").replace("\n", "")
        check("再読み込み後もサーバーの目標が出る", "次の練習バックフル" in plan_text, plan_text)
        page.screenshot(path=str(SHOT_DIR / "08_after_save_trick.png"), full_page=True)
        all_errors += errors
        page.close()

        # 7. リンクなし／存在しない選手
        page, errors = open_page(browser, base, MockBackend(EVENTS), "")
        page.wait_for_selector("[data-testid=no-athlete]")
        check("?a=なし: 専用リンクの案内", True)
        all_errors += errors
        page.close()
        page, errors = open_page(browser, base, MockBackend(EVENTS), "?a=unknown")
        page.wait_for_selector("[data-testid=broken-link]")
        check("?a=存在しない: 選手が見つからない案内", True)
        all_errors += errors
        page.close()

        # 8. コーチ画面が表示だけできる（書き込みは本番APIで別途確認）
        page, errors = open_page(browser, base, MockBackend(EVENTS), "?coach=1")
        page.wait_for_selector("text=登録済みの練習日")
        check("コーチ画面: 練習日の一覧が出る", page.locator(".event-row").count() == 4)
        page.screenshot(path=str(SHOT_DIR / "09_coach.png"), full_page=True)
        all_errors += errors
        page.close()

        browser.close()
    server.shutdown()

    check("JSエラー0件（pageerror / console.error）", not all_errors, "; ".join(all_errors))
    failed = [r for r in results if not r[1]]
    print("\n%d件中 %d件OK" % (len(results), len(results) - len(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
