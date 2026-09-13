/* MIC 次の練習 — Apps Script Web App（スプレッドシートにバインドして使う）
   シート「練習日」: event_id, 日付, 区分, 場所, 備考（コーチが管理画面から入力）
   シート「目標」  : plan_id, athlete_id, event_id, 良くしたいこと, 確かめること, 作成日時, 状態
   選手名簿はこのアプリでは持たない（MICエアlogのAPIから画面側で読む）。

   状態は「有効」と「作り直し」の2つだけ。未達・達成のような状態は持たない。
   同じ選手・同じ練習日で保存し直すと、前の目標は「作り直し」になる（繰り越しはしない）。

   コーチ用の書き込み（練習日の追加・修正・削除）はスクリプトプロパティ COACH_KEY と照合する。
   キーの値はコードに書かない。プロジェクトの設定 → スクリプト プロパティ で設定する。 */

var TZ = 'Asia/Tokyo';
var SHEET_EVENTS = '練習日';
var SHEET_PLANS = '目標';
var EVENT_HEADERS = ['event_id', '日付', '区分', '場所', '備考'];
var PLAN_HEADERS = ['plan_id', 'athlete_id', 'event_id', '良くしたいこと', '確かめること', '作成日時', '状態'];
var KUBUN = ['午前', '午後', '終日'];
var STATUS_ACTIVE = '有効';
var STATUS_REPLACED = '作り直し';
var MAX_TEXT = 100;

/* 初回だけエディタから実行する。シートと見出し行を作る（既にあれば何もしない）。 */
function setup() {
  ensureSheet(SHEET_EVENTS, EVENT_HEADERS);
  ensureSheet(SHEET_PLANS, PLAN_HEADERS);
}

function ensureSheet(name, headers) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (sheet.getLastRow() === 0) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

/* GET ?a=<athleteId> : 練習日すべて ＋ その選手の有効な目標
   GET（aなし）       : 練習日すべて（コーチ画面用） */
function doGet(e) {
  try {
    var athleteId = (e && e.parameter && e.parameter.a) ? String(e.parameter.a) : '';
    var plans = athleteId ? readPlans().filter(function (p) {
      return p.athleteId === athleteId && p.status === STATUS_ACTIVE;
    }) : [];
    return json({ ok: true, events: readEvents(), plans: plans });
  } catch (err) {
    return json({ ok: false, error: String(err && err.message || err) });
  }
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
    var payload = JSON.parse(e.postData.contents);
    switch (payload.type) {
      case 'savePlan': return json(savePlan(payload));
      case 'checkCoachKey': requireCoach(payload); return json({ ok: true });
      case 'addEvent': requireCoach(payload); return json(addEvent(payload));
      case 'updateEvent': requireCoach(payload); return json(updateEvent(payload));
      case 'deleteEvent': requireCoach(payload); return json(deleteEvent(payload));
      default: return json({ ok: false, error: 'unknown type' });
    }
  } catch (err) {
    return json({ ok: false, error: String(err && err.message || err) });
  } finally {
    lock.releaseLock();
  }
}

/* ---- 読み取り ---- */

function cellDate(v) {
  if (v instanceof Date) return Utilities.formatDate(v, TZ, 'yyyy-MM-dd');
  return String(v || '');
}
function cellDateTime(v) {
  if (v instanceof Date) return Utilities.formatDate(v, TZ, 'yyyy-MM-dd HH:mm:ss');
  return String(v || '');
}

function readEvents() {
  var sheet = ensureSheet(SHEET_EVENTS, EVENT_HEADERS);
  var values = sheet.getDataRange().getValues().slice(1);
  return values.filter(function (r) { return r[0]; }).map(function (r) {
    return { eventId: String(r[0]), date: cellDate(r[1]), kubun: String(r[2] || ''), place: String(r[3] || ''), note: String(r[4] || '') };
  }).sort(function (a, b) {
    if (a.date !== b.date) return a.date < b.date ? -1 : 1;
    return KUBUN.indexOf(a.kubun) - KUBUN.indexOf(b.kubun);
  });
}

function readPlans() {
  var sheet = ensureSheet(SHEET_PLANS, PLAN_HEADERS);
  var values = sheet.getDataRange().getValues().slice(1);
  return values.filter(function (r) { return r[0]; }).map(function (r) {
    return { planId: String(r[0]), athleteId: String(r[1]), eventId: String(r[2]), improve: String(r[3] || ''), check: String(r[4] || ''), createdAt: cellDateTime(r[5]), status: String(r[6] || '') };
  });
}

/* ---- 書き込み ---- */

/* 文字列はすべて先頭に ' を付けて書く。日付っぽい文字列の自動変換と、= で始まる入力が数式になるのを防ぐ。 */
function asText(v) { return "'" + String(v); }

function cleanText(v, label, required) {
  var s = String(v == null ? '' : v).trim();
  if (required && !s) throw new Error(label + 'が空です');
  if (s.length > MAX_TEXT) throw new Error(label + 'が長すぎます');
  return s;
}

function validDate(s) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) throw new Error('日付の形式が正しくありません');
  return s;
}

function findRow(sheet, id) {
  var ids = sheet.getRange(1, 1, Math.max(sheet.getLastRow(), 1), 1).getValues();
  for (var i = 1; i < ids.length; i++) { if (String(ids[i][0]) === String(id)) return i + 1; }
  return -1;
}

function newId(prefix) { return prefix + Utilities.getUuid().replace(/-/g, '').slice(0, 10); }

function savePlan(p) {
  var athleteId = cleanText(p.athleteId, '選手ID', true);
  var eventId = cleanText(p.eventId, '練習日', true);
  var improve = cleanText(p.improve, '良くしたいこと', true);
  var check = cleanText(p.check, '確かめること', true);
  if (!readEvents().some(function (ev) { return ev.eventId === eventId; })) throw new Error('練習日が見つかりません');

  var sheet = ensureSheet(SHEET_PLANS, PLAN_HEADERS);
  var values = sheet.getDataRange().getValues();
  for (var i = 1; i < values.length; i++) {
    if (String(values[i][1]) === athleteId && String(values[i][2]) === eventId && String(values[i][6]) === STATUS_ACTIVE) {
      sheet.getRange(i + 1, 7).setValue(STATUS_REPLACED);
    }
  }
  var plan = { planId: newId('p'), athleteId: athleteId, eventId: eventId, improve: improve, check: check, createdAt: Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd HH:mm:ss'), status: STATUS_ACTIVE };
  sheet.appendRow([plan.planId, asText(athleteId), plan.eventId, asText(improve), asText(check), asText(plan.createdAt), STATUS_ACTIVE]);
  return { ok: true, plan: plan };
}

function requireCoach(p) {
  var key = PropertiesService.getScriptProperties().getProperty('COACH_KEY');
  if (!key) throw new Error('COACH_KEY が未設定です');
  if (String(p.coachKey || '') !== key) throw new Error('コーチ用キーが違います');
}

function eventFields(p) {
  var kubun = String(p.kubun || '');
  if (KUBUN.indexOf(kubun) < 0) throw new Error('区分が正しくありません');
  return { date: validDate(String(p.date || '')), kubun: kubun, place: cleanText(p.place, '場所', false), note: cleanText(p.note, '備考', false) };
}

function addEvent(p) {
  var f = eventFields(p);
  var sheet = ensureSheet(SHEET_EVENTS, EVENT_HEADERS);
  var eventId = newId('e');
  sheet.appendRow([eventId, asText(f.date), f.kubun, asText(f.place), asText(f.note)]);
  return { ok: true, events: readEvents() };
}

function updateEvent(p) {
  var f = eventFields(p);
  var sheet = ensureSheet(SHEET_EVENTS, EVENT_HEADERS);
  var row = findRow(sheet, p.eventId);
  if (row < 0) throw new Error('練習日が見つかりません');
  sheet.getRange(row, 2, 1, 4).setValues([[asText(f.date), f.kubun, asText(f.place), asText(f.note)]]);
  return { ok: true, events: readEvents() };
}

/* 練習日を消しても、その日に紐づく目標の行は残す（履歴として。画面には出なくなる）。 */
function deleteEvent(p) {
  var sheet = ensureSheet(SHEET_EVENTS, EVENT_HEADERS);
  var row = findRow(sheet, p.eventId);
  if (row < 0) throw new Error('練習日が見つかりません');
  sheet.deleteRow(row);
  return { ok: true, events: readEvents() };
}
