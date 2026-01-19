import requests
from bs4 import BeautifulSoup
import time
import re
from datetime import datetime
from .database import Race, Horse, Entry, Result

class JRAScraper:
    BASE_URL = "https://www.jra.go.jp"
    
    def __init__(self, db_session):
        self.session = db_session
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def fetch_page(self, url):
        time.sleep(1) # Be polite
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            return BeautifulSoup(response.text, 'html.parser')
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return None

    def scrape_race_card(self, url):
        """
        出馬表をスクレイピングする (Method stub)
        Example URL: https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1006202301010120230105/FE
        Note: JRA URLs are complex and often require POST or specific parameters.
        For simplicity, we might parse specific HTML structures if we have the direct link.
        """
        pass

    def scrape_race_results(self, url):
        """
        レース結果をスクレイピングする
        """
        soup = self.fetch_page(url)
        if not soup:
            return None
            
        try:
            # レース情報の取得
            race_name_elem = soup.select_one('h1.title_race') or soup.select_one('div.race_name')
            race_name = race_name_elem.get_text(strip=True) if race_name_elem else "Unknown Race"
            
            # 開催詳細 (距離、コースなど)
            # data_intro class内に詳細がある場合が多い
            details_text = ""
            details_elem = soup.select_one('div.race_data') # 仮のセレクタ
            if details_elem:
                details_text = details_elem.get_text(strip=True)
            
            # 日付の取得 (URLやページ内から) - ここでは現在日またはURLパラメータから推測が必要だが簡易化
            race_date = datetime.now().date() 

            race = Race(
                id=url.split('?')[-1], # 簡易ID (実際はURLのパラメータを解析すべき)
                name=race_name,
                date=race_date,
                location="Unknown", # TODO: Parse from text
                course_type="Unknown", # TODO: Parse from text
                distance=0, # TODO: Parse from text
                weather="Unknown",
                track_condition="Unknown"
            )
            
            entries = []
            results = []
            
            # 結果テーブルの解析
            table = soup.select_one('table.type01') or soup.find('table', class_=re.compile('basic'))
            if not table:
                print("Table not found")
                return None
                
            rows = table.find_all('tr')
            for row in rows:
                # ヘッダー行スキップ
                if row.find('th'):
                    continue
                    
                cols = row.find_all('td')
                if not cols:
                    continue
                
                # JRAの結果テーブル構造 (着順, 枠, 馬番, 馬名, 性齢, 斤量, 騎手, タイム, 着差, ...)
                # クラス名があればそれを使う
                place_elem = row.select_one('td.place')
                horse_elem = row.select_one('td.horse')
                jockey_elem = row.select_one('td.jockey')
                
                # クラスがない場合のインデックスフォールバック (標準的な並びを仮定)
                place_text = place_elem.get_text(strip=True) if place_elem else cols[0].get_text(strip=True)
                horse_name = horse_elem.get_text(strip=True) if horse_elem else cols[3].get_text(strip=True)
                jockey_name = jockey_elem.get_text(strip=True) if jockey_elem else cols[6].get_text(strip=True)
                
                # 着順が数字でない場合（取消、中止など）はスキップまたは特殊扱い
                if not place_text.isdigit():
                    continue
                    
                rank = int(place_text)
                
                # 馬データの作成/取得
                horse_id = horse_name # 本来はIDが必要だが名前で代用
                horse = Horse(id=horse_id, name=horse_name)
                
                # エントリー作成
                entry = Entry(
                    race_id=race.id,
                    horse_id=horse.id,
                    jockey=jockey_name,
                    # 他のフィールドは取得できれば埋める
                )
                
                # 結果作成
                result = Result(
                    race_id=race.id,
                    horse_id=horse.id,
                    rank=rank
                    # タイムなども取得可能なら
                )
                
                entries.append(entry)
                results.append(result)
                
            return {
                'race': race,
                'entries': entries,
                'results': results
            }
            
        except Exception as e:
            print(f"Error parsing race data: {e}")
            import traceback
            traceback.print_exc()
            return None

    def save_to_db(self, parsed_data):
        if not parsed_data:
            return
            
        try:
            self.session.merge(parsed_data['race'])
            for entry in parsed_data['entries']:
                # 重複チェックが必要だが、mergeで簡易対応
                # Entryは複合主キーではないため、ID管理が微妙。実際はaddでUnique制約エラーを避ける処理が必要
                self.session.merge(entry) 
                
            for result in parsed_data['results']:
                self.session.add(result)
                
            self.session.commit()
            print("Saved race data")
        except Exception as e:
            self.session.rollback()
            print(f"DB Error: {e}")

