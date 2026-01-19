import streamlit as st

st.set_page_config(page_title="JRA Tracking App", layout="wide")

st.title("JRA 競馬予測 (Bayesian Inference)")
st.write("左側のサイドバーから機能を選択してください。")

st.sidebar.title("メニュー")
option = st.sidebar.selectbox("機能", ["ダッシュボード", "データ収集", "分析・予測"])

if option == "ダッシュボード":
    st.header("開催予定のレース")
    st.info("データがありません。データ収集を実行してください。")
elif option == "データ収集":
    st.header("データスクレイピング")
    st.write("JRA公式サイトからデータを取得します。")
    
    url = st.text_input("レース結果URLを入力してください", "https://www.jra.go.jp/JRADB/accessS.html?CNAME=pw01sde1006202601060120260117/85")
    
    if st.button("データ取得開始"):
        from data.scraper import JRAScraper
        from data.database import init_db
        
        session = init_db()
        scraper = JRAScraper(session)
        
        with st.spinner("スクレイピング中..."):
            data = scraper.scrape_race_results(url)
            if data:
                st.success(f"データ取得成功: {data['race'].name}")
                st.write(f"エントリー数: {len(data['entries'])}")
                st.dataframe([{'Rank': r.rank, 'Horse': e.horse_id, 'Jockey': e.jockey} 
                              for r, e in zip(data['results'], data['entries'])])
                scraper.save_to_db(data)
                st.info("データがデータベースに保存されました。")
            else:
                st.error("データ取得に失敗しました。URLを確認するか、ページ構造が変わっている可能性があります。")

elif option == "分析・予測":
    st.header("ベイズ推定モデル")
    st.write("Stanモデルを用いて予測を行います。")
    
    from data.database import init_db, Result, Entry, Horse
    import pandas as pd
    
    if st.button("モデル学習 (データ更新)"):
        with st.spinner("学習中..."):
            session = init_db()
            # データを取得してDataFrame化
            results = session.query(Result).all()
            if not results:
                st.warning("学習用データがありません。「データ収集」を行ってください。")
            else:
                data = []
                for r in results:
                    # 馬名や騎手名も取得する必要があるが、ResultにはIDしかないのでJoinが必要
                    # 簡易的にResultのIDだけで進めるか、Joinクエリを書く
                    # EntryからJockey情報を取るのが一意
                     entry = session.query(Entry).filter_by(race_id=r.race_id, horse_id=r.horse_id).first()
                     if entry:
                         # Get horse name
                         horse_name = entry.horse.name if entry.horse else r.horse_id
                         
                         data.append({
                             'rank': r.rank,
                             'jockey': entry.jockey,
                             'horse_id': horse_name
                         })
                
                if not data:
                    st.error("有効な学習データが抽出できませんでした。")
                else:
                    df = pd.DataFrame(data)
                    
                    from analysis.predictor import JRAPredictor
                    predictor = JRAPredictor()
                    summary = predictor.train(df)
                    
                    st.success("学習完了")
                    st.success("学習完了")
                    

                    # --- 騎手ランキング ---
                    st.subheader("騎手能力ランキング (beta_j)")
                    st.write("数値が大きいほど、このモデルが「強い（勝率が高い）」と評価している騎手です。")
                    
                    id_to_jockey_name = {v: k for k, v in predictor.jockey_map.items()}
                    beta_j_rows = []
                    for i in range(1, len(id_to_jockey_name) + 1):
                        param_name = f'beta_j[{i}]'
                        if param_name in summary.index:
                            row = summary.loc[param_name]
                            beta_j_rows.append({
                                'Jockey': id_to_jockey_name[i],
                                'Ability': row['Mean'],
                                'Uncertainty': row['StdDev'],
                                'Lower 5%': row['5%'],
                                'Upper 95%': row['95%'],
                                'R_hat': row['R_hat']
                            })
                    
                    if beta_j_rows:
                        jockey_df = pd.DataFrame(beta_j_rows).set_index('Jockey').sort_values('Ability', ascending=False)
                        st.dataframe(jockey_df, use_container_width=True)

                    # --- 馬ランキング ---
                    st.subheader("馬能力ランキング (beta_h)")
                    st.write("数値が大きいほど、このモデルが「強い」と評価している馬です。")
                    
                    id_to_horse_name = {v: k for k, v in predictor.horse_map.items()}
                    beta_h_rows = []
                    for i in range(1, len(id_to_horse_name) + 1):
                        param_name = f'beta_h[{i}]'
                        if param_name in summary.index:
                            row = summary.loc[param_name]
                            beta_h_rows.append({
                                'Horse': id_to_horse_name[i],
                                'Ability': row['Mean'],
                                'Uncertainty': row['StdDev'],
                                'Lower 5%': row['5%'],
                                'Upper 95%': row['95%'],
                                'R_hat': row['R_hat']
                            })
                            
                    if beta_h_rows:
                        horse_df = pd.DataFrame(beta_h_rows).set_index('Horse').sort_values('Ability', ascending=False)
                        st.dataframe(horse_df, use_container_width=True)
                    else:
                        st.write("馬データの表示に失敗しました。")
                    
                    # 簡易的な可視化（騎手能力の上位表示など）
                    # 実際はsummaryからbeta_jを取り出す

