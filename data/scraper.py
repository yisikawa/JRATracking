import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime, date
from .database import Race, Horse, Entry, Result, Jockey

_JOCKEY_SYMBOL_RE = re.compile(r'^[▲△☆◇★◎○✕×\s]+')


def _normalize_jockey(name: str) -> str:
    return _JOCKEY_SYMBOL_RE.sub('', name).strip()


def _extract_jockey_id(link) -> str:
    if not link:
        return None
    href = link.get('href', '')
    m = re.search(r'/jockey/(?:result/recent/)?(\w+)/?', href)
    return m.group(1) if m else None

PLACE_CODES = {
    '01': '札幌', '02': '函館', '03': '福島', '04': '新潟', '05': '東京',
    '06': '中山', '07': '中京', '08': '京都', '09': '阪神', '10': '小倉'
}


class JRAScraper:
    DB_BASE = "https://db.netkeiba.com"
    RACE_LIST_URL = "https://race.netkeiba.com/top/race_list.html"

    def __init__(self, db_session):
        self.session = db_session
        self.http = requests.Session()
        self.http.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
        })
        self._cookie_initialized = False

    def _ensure_cookies(self):
        if not self._cookie_initialized:
            try:
                self.http.get('https://race.netkeiba.com/', timeout=10)
                self._cookie_initialized = True
            except Exception:
                pass

    def fetch_page(self, url, encoding='EUC-JP', referer: str = None):
        time.sleep(1)
        try:
            headers = {'Referer': referer} if referer else {}
            response = self.http.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            response.encoding = encoding
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def get_race_ids_by_date(self, target_date: date) -> list:
        """指定日のJRAレースID一覧を取得する。
        レース結果はレース終了後にnetkeibaへ反映されるため、
        当日開催中のレースは取得できない場合がある。
        """
        date_str = target_date.strftime('%Y%m%d')
        url = f"{self.DB_BASE}/race/list/{date_str}/"
        soup = self.fetch_page(url, encoding='EUC-JP', referer=self.DB_BASE)
        if not soup:
            return []

        race_ids = []
        for a in soup.find_all('a', href=True):
            m = re.search(r'/race/(\d{12})/', a['href'])
            if m:
                race_id = m.group(1)
                # JRAのみ (venue code 01-10)
                venue_code = int(race_id[4:6])
                if 1 <= venue_code <= 10 and race_id not in race_ids:
                    race_ids.append(race_id)
        return sorted(race_ids)

    def get_upcoming_race_ids(self, target_date: date) -> list:
        """当日・翌日など結果未確定日のJRAレースID一覧を取得する。
        race_list_sub.html は静的HTMLで返るため当日レースにも対応。
        """
        self._ensure_cookies()
        date_str = target_date.strftime('%Y%m%d')
        url = f"https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={date_str}"
        soup = self.fetch_page(url, encoding='utf-8', referer='https://race.netkeiba.com/')
        if not soup:
            return []

        race_ids = []
        for a in soup.find_all('a', href=True):
            m = re.search(r'race_id=(\d{12})', a['href'])
            if m:
                race_id = m.group(1)
                venue_code = int(race_id[4:6])
                if 1 <= venue_code <= 10 and race_id not in race_ids:
                    race_ids.append(race_id)
        return sorted(race_ids)

    def _find_entry_table(self, soup) -> object:
        """ページ内の出走馬テーブルを探す（クラス名に依存しない）"""
        # クラス名で検索
        table = (
            soup.select_one('table.Shutuba_Table') or
            soup.select_one('table[class*="Shutuba"]') or
            soup.select_one('table[class*="shutuba"]') or
            soup.select_one('table[class*="RaceCard"]') or
            soup.select_one('table[class*="race_card"]')
        )
        if table:
            return table
        # ヒューリスティック: 行数>=8 かつ先頭データセルが枠番(1桁数字)のテーブル
        for t in soup.find_all('table'):
            data_rows = [r for r in t.find_all('tr') if r.find('td')]
            if len(data_rows) < 6:
                continue
            first_td = data_rows[0].find('td')
            if first_td and re.match(r'^\d$', first_td.get_text(strip=True)):
                return t
        return None

    def scrape_shutuba(self, race_id: str) -> dict:
        """出馬表をスクレイピングしてレース情報と出走馬リストを返す。
        results が未確定の当日レースにも対応。
        """
        self._ensure_cookies()

        # ① メインサイト (UTF-8)
        url_main = f"https://race.netkeiba.com/race/shutuba.html?race_id={race_id}&rf=race_list"
        soup = self.fetch_page(url_main, encoding='utf-8',
                               referer='https://race.netkeiba.com/top/race_list_sub.html')
        table = self._find_entry_table(soup) if soup else None

        # ② サブページ (JS非依存の静的版)
        if not table:
            url_sub = f"https://race.netkeiba.com/race/shutuba_sub.html?race_id={race_id}"
            soup2 = self.fetch_page(url_sub, encoding='utf-8',
                                    referer='https://race.netkeiba.com/top/race_list_sub.html')
            table2 = self._find_entry_table(soup2) if soup2 else None
            if table2:
                soup, table = soup2, table2

        # ③ モバイル版 (sp.netkeiba.com / UTF-8 / SSR)
        if not table:
            url_sp = f"https://sp.netkeiba.com/race/card.html?race_id={race_id}"
            soup3 = self.fetch_page(url_sp, encoding='utf-8',
                                    referer='https://sp.netkeiba.com/')
            table3 = self._find_entry_table(soup3) if soup3 else None
            if table3:
                soup, table = soup3, table3
                print(f"[shutuba] モバイル版で取得成功")

        if not soup:
            return {'_error': 'ページ取得失敗'}

        # レース名
        race_name_elem = soup.select_one('h1.RaceName') or soup.select_one('.RaceName') or soup.find('h1')
        race_name = race_name_elem.get_text(strip=True) if race_name_elem else f"Race {race_id}"

        # コース・距離・天候など
        details_text = soup.get_text()
        course_type, distance = "Unknown", 0
        m = re.search(r'(芝|ダート|ダ|障害|障)(\d+)m', details_text)
        if m:
            course_map = {'芝': '芝', 'ダート': 'ダート', 'ダ': 'ダート', '障害': '障害', '障': '障害'}
            course_type = course_map.get(m.group(1), m.group(1))
            distance = int(m.group(2))

        weather = ""
        m = re.search(r'天候\s*[：:]\s*(\S+)', details_text)
        if m:
            weather = m.group(1)

        place_code = race_id[4:6]
        location = PLACE_CODES.get(place_code, f"場所{place_code}")
        race_num = int(race_id[10:12])

        if not table:
            all_tables = [t.get('class') for t in soup.find_all('table')]
            page_title = soup.title.string.strip() if soup.title else 'N/A'
            # デバッグ情報にスクレイピング先の生テキストを含めない
            # (Windowsコンソールのcp932でエンコードできない文字が混入しクラッシュするため)
            print(f"[shutuba] テーブル未検出 race_id={race_id}, 検出テーブル={all_tables[:8]}")
            not_published = any(kw in details_text for kw in ['出馬表はまだ', '公開されていません', '発表前', '登録受付'])
            error_msg = '出馬表はまだ公開されていません（通常レース3〜4日前に公開）' if not_published else '出馬表テーブルが見つかりません'
            return {
                '_error': error_msg,
                '_page_title': page_title,
                '_tables': all_tables[:8],
            }

        all_rows = table.find_all('tr')
        print(f"[shutuba] テーブル検出: {table.get('class')}, 行数={len(all_rows)}")

        entries = []
        for row in all_rows:
            cols = row.find_all('td')
            if len(cols) < 7:
                continue

            bracket_text = cols[0].get_text(strip=True)
            if not re.match(r'^\d+$', bracket_text):
                continue

            bracket_num = int(bracket_text)
            horse_num_text = cols[1].get_text(strip=True)
            horse_num = int(horse_num_text) if re.match(r'^\d+$', horse_num_text) else 0

            # 馬名・馬ID (col[3])
            horse_link = cols[3].find('a')
            horse_name = cols[3].get_text(strip=True)
            horse_id = horse_name
            if horse_link and horse_link.get('href'):
                mm = re.search(r'/horse/(\w+)', horse_link['href'])
                if mm:
                    horse_id = mm.group(1)

            # 性齢 (col[4])
            sexa_text = cols[4].get_text(strip=True)
            sex_match = re.match(r'([牡牝セ])(\d+)', sexa_text)
            sex = sex_match.group(1) if sex_match else ""
            age = int(sex_match.group(2)) if sex_match else 0

            # 斤量 (col[5])
            weight_text = cols[5].get_text(strip=True)
            weight = float(weight_text) if re.match(r'^\d+(\.\d+)?$', weight_text) else 0.0

            # 騎手名・騎手ID (col[6])
            jockey_link = cols[6].find('a')
            jockey_name = _normalize_jockey(cols[6].get_text(strip=True))
            jockey_id   = _extract_jockey_id(jockey_link)

            # 調教師 (col[7])
            trainer_name = cols[7].get_text(strip=True) if len(cols) > 7 else ""

            entries.append({
                'bracket_number': bracket_num,
                'horse_number':   horse_num,
                'horse_name':     horse_name,
                'horse_id':       horse_id,
                'sex':            sex,
                'age':            age,
                'weight':         weight,
                'jockey':         jockey_name,
                'jockey_id':      jockey_id,
                'trainer':        trainer_name,
            })

        return {
            'race_id':     race_id,
            'race_name':   race_name,
            'race_number': race_num,
            'location':    location,
            'course_type': course_type,
            'distance':    distance,
            'weather':     weather,
            'entries':     entries,
        }

    def _extract_race_id(self, race_id_or_url: str) -> str:
        """URLまたは文字列から12桁のrace_idを取得する"""
        m = re.search(r'race_id=(\d{12})', race_id_or_url)
        if m:
            return m.group(1)
        m = re.search(r'/race/(\d{12})/?', race_id_or_url)
        if m:
            return m.group(1)
        if re.match(r'^\d{12}$', race_id_or_url.strip()):
            return race_id_or_url.strip()
        return race_id_or_url.strip()

    def scrape_race_results(self, race_id_or_url: str) -> dict:
        """レース結果をスクレイピングする。race_id(12桁)またはURLを受け付ける"""
        race_id = self._extract_race_id(race_id_or_url)
        url = f"{self.DB_BASE}/race/{race_id}/"

        soup = self.fetch_page(url, encoding='EUC-JP')
        if not soup:
            return None

        try:
            # サイト共通ヘッダーのロゴにも<h1>があり文書内先頭に来るため、
            # レース詳細ブロック(dl.racedata)内のh1を優先し、
            # 見つからない場合はテキストを持つ最初のh1にフォールバックする
            race_name_elem = (
                soup.select_one('dl.racedata h1') or
                next((h for h in soup.find_all('h1') if h.get_text(strip=True)), None)
            )
            race_name = race_name_elem.get_text(strip=True) if race_name_elem else f"Race {race_id}"

            # ページ全体からレース詳細テキストを収集
            details_text = ""
            for selector in ['div.data_intro', 'div.mainrace_data', 'p.smalltxt', '.race_data']:
                elem = soup.select_one(selector)
                if elem:
                    details_text += " " + elem.get_text()

            course_type = "Unknown"
            distance = 0
            weather = "Unknown"
            track_condition = "Unknown"
            race_date = datetime.now().date()

            m = re.search(r'(芝|ダート|ダ|障害|障)(\d+)m', details_text)
            if m:
                course_map = {'芝': '芝', 'ダート': 'ダート', 'ダ': 'ダート', '障害': '障害', '障': '障害'}
                course_type = course_map.get(m.group(1), m.group(1))
                distance = int(m.group(2))

            m = re.search(r'天候\s*[：:]\s*(\S+)', details_text)
            if m:
                weather = m.group(1)

            m = re.search(r'(?:馬場|芝|ダート)\s*[：:]\s*(\S+)', details_text)
            if m:
                track_condition = m.group(1)

            m = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', details_text)
            if m:
                race_date = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            else:
                # race_idの先頭4桁が年
                try:
                    race_date = date(int(race_id[:4]), 1, 1)
                except ValueError:
                    pass

            place_code = race_id[4:6]
            location = PLACE_CODES.get(place_code, f"場所{place_code}")

            race = Race(
                id=race_id,
                name=race_name,
                date=race_date,
                location=location,
                course_type=course_type,
                distance=distance,
                weather=weather,
                track_condition=track_condition
            )

            table = soup.select_one('table.race_table_01')
            if not table:
                print(f"Result table not found for {race_id} (URL: {url})")
                return None

            horses, entries, results = [], [], []

            # netkeiba 結果テーブルの列順:
            # 0:着順 1:枠番 2:馬番 3:馬名 4:性齢 5:斤量 6:騎手 7:タイム 8:着差 9:上がり 10:人気 11:単勝 ...
            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 8:
                    continue

                place_text = cols[0].get_text(strip=True)
                if not re.match(r'^\d+$', place_text):
                    continue
                rank = int(place_text)

                bracket_text = cols[1].get_text(strip=True)
                bracket_num = int(bracket_text) if re.match(r'^\d+$', bracket_text) else 0

                horse_num_text = cols[2].get_text(strip=True)
                horse_num = int(horse_num_text) if re.match(r'^\d+$', horse_num_text) else 0

                horse_link = cols[3].find('a')
                horse_name = cols[3].get_text(strip=True)
                horse_id = horse_name
                if horse_link and horse_link.get('href'):
                    m = re.search(r'/horse/(\w+)/?', horse_link['href'])
                    if m:
                        horse_id = m.group(1)

                # 性齢: 列4 e.g. "牡3" "牝5" "セ4"
                sexa_text = cols[4].get_text(strip=True)
                sex_match = re.match(r'([牡牝セ])(\d+)', sexa_text)
                sex = sex_match.group(1) if sex_match else ""
                age = int(sex_match.group(2)) if sex_match else 0

                weight_text = cols[5].get_text(strip=True)
                weight = float(weight_text) if re.match(r'^\d+(\.\d+)?$', weight_text) else 0.0

                jockey_link  = cols[6].find('a')
                jockey_name  = _normalize_jockey(cols[6].get_text(strip=True))
                jockey_id_val = _extract_jockey_id(jockey_link)

                time_seconds = self._parse_time(cols[7].get_text(strip=True))

                # 単勝オッズ: 列11 (上がり/着差の後)
                odds = None
                if len(cols) > 11:
                    odds_text = cols[11].get_text(strip=True)
                    if re.match(r'^\d+(\.\d+)?$', odds_text):
                        odds = float(odds_text)

                # 調教師: 通常列13か14
                trainer_name = ""
                for col_idx in [13, 14]:
                    if len(cols) > col_idx:
                        txt = cols[col_idx].get_text(strip=True)
                        if txt and not re.match(r'^[\d\.\-\s]+$', txt):
                            trainer_name = txt
                            break

                horses.append(Horse(id=horse_id, name=horse_name, sex=sex, age=age))
                entries.append(Entry(
                    race_id=race_id,
                    horse_id=horse_id,
                    bracket_number=bracket_num,
                    horse_number=horse_num,
                    jockey=jockey_name,
                    jockey_id=jockey_id_val,
                    trainer=trainer_name,
                    weight=weight
                ))
                results.append(Result(
                    race_id=race_id,
                    horse_id=horse_id,
                    rank=rank,
                    time_seconds=time_seconds,
                    odds=odds
                ))

            if not results:
                print(f"No results parsed for {race_id}")
                return None

            return {'race': race, 'horses': horses, 'entries': entries, 'results': results}

        except Exception as e:
            print(f"Error parsing race {race_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _parse_time(self, time_str: str):
        """'1:34.5' → 94.5、'58.3' → 58.3 のように秒数に変換する"""
        m = re.match(r'(\d+):(\d+)\.(\d+)', time_str)
        if m:
            return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 10
        m = re.match(r'^\d+\.\d+$', time_str)
        if m:
            return float(time_str)
        return None

    def save_to_db(self, parsed_data: dict):
        if not parsed_data:
            return
        try:
            self.session.merge(parsed_data['race'])
            for horse in parsed_data['horses']:
                self.session.merge(horse)
            for entry in parsed_data['entries']:
                if entry.jockey_id:
                    self.session.merge(Jockey(id=entry.jockey_id, name=entry.jockey))
            for entry in parsed_data['entries']:
                existing = self.session.query(Entry).filter_by(
                    race_id=entry.race_id, horse_id=entry.horse_id
                ).first()
                if not existing:
                    self.session.add(entry)
            for result in parsed_data['results']:
                existing = self.session.query(Result).filter_by(
                    race_id=result.race_id, horse_id=result.horse_id
                ).first()
                if not existing:
                    self.session.add(result)
            self.session.commit()
            print(f"Saved race {parsed_data['race'].id}: {parsed_data['race'].name}")
        except Exception as e:
            self.session.rollback()
            print(f"DB Error: {e}")
