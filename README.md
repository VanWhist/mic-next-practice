# MIC 次の練習（第1版）

ジュニアモーグル選手が自分のスマホで開く小さなアプリ。
「ウォータージャンプ、あと◯日」を先に見せて、次の練習で良くしたいことを1つ、それを何で確かめるかを1つ決める。

- 選手画面: `index.html?a=<athleteId>`（MICエアlogの専用リンクと同じID）
- コーチ画面: `index.html?coach=1`（練習日の追加・修正・削除）
- 選手名簿と最近の技: MICエアlogのAPIを読むだけ（書き込まない）

## 第1版で持たないもの

本数の合計・配分・必要本数／達成率・連続達成・ランキング・未達表示／繰り越し／保護者入力・参加者一覧／Googleカレンダー連携。
本数は上限であって目標ではない。予定と実績がズレたら「作り直す」。

## バックエンド（2026-09-13 作成済み）

- スプレッドシート「MIC次の練習」: https://docs.google.com/spreadsheets/d/1ZBsPkgTF2l2PgX1TFoXzD4TY9khfQzVq7jvus-11Z-U/edit
- Apps Script「MIC次の練習 API」（上のシートにバインド）: https://script.google.com/u/0/home/projects/1dOSVYDH9ybz4OFOrNyUq14yjO22rzE16Ai5XtIGTq6UPGMCKu5PNlBIm/edit
- Web App（バージョン1）: https://script.google.com/macros/s/AKfycbxbFOiI0Hy61u_OGzB1v_qaRQgdIUeb5o5SpSSySPnllKMp9GOQ-QMqM_5GVHFGpdbm/exec
- COACH_KEY はスクリプトプロパティに設定済み（値はここに書かない）

## バックエンドを作り直す場合の手順

1. Googleスプレッドシートを新規作成（名前例: `MIC次の練習`）
2. 拡張機能 → Apps Script を開き、`gas/Code.gs` の中身を貼って保存
3. 関数 `setup` を選んで実行（シート「練習日」「目標」と見出し行ができる。初回は承認画面が出る）
4. プロジェクトの設定 → スクリプト プロパティ に `COACH_KEY` を追加（値はコーチ同士で共有する合言葉。コードやこのリポジトリには書かない）
5. デプロイ → 新しいデプロイ → 種類: ウェブアプリ／実行ユーザー: 自分／アクセス: 全員
6. 出てきた `/exec` のURLを `index.html` の `NEXT_API_URL` に入れる

コードを直したら「デプロイを管理 → 編集 → 新バージョン」で同じURLのまま反映する。

## 検証

```
python tests/test_app.py [スクリーンショットの保存先]
```

Playwright（Chromium）、幅430px、外部APIはすべてモック。
