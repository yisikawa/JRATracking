import streamlit as st

st.set_page_config(page_title="JRA Tracking App", layout="wide")

st.title("JRA 競馬予測 (Bayesian Inference)")
st.write("左側のサイドバーから機能を選択してください。")

st.sidebar.title("メニュー")
option = st.sidebar.selectbox("機能", ["ダッシュボード", "データ収集", "分析・予測", "データベース管理"])

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

elif option == "データベース管理":
    st.header("データベース管理")
    from data.database import init_db, Race, Horse, Entry, Result
    import pandas as pd
    from sqlalchemy import text
    import io

    session = init_db()

    # Database Statistics
    st.subheader("データベース統計")
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Races", session.query(Race).count())
    col2.metric("Horses", session.query(Horse).count())
    col3.metric("Entries", session.query(Entry).count())
    col4.metric("Results", session.query(Result).count())

    # Tabs for operations
    tab1, tab2, tab3 = st.tabs(["データ閲覧/削除", "インポート/エクスポート", "メンテナンス"])

    with tab1:
        st.subheader("データ閲覧・削除")
        table_name = st.selectbox("テーブルを選択", ["Races", "Horses", "Entries", "Results"])
        
        # Load Data
        model_map = {"Races": Race, "Horses": Horse, "Entries": Entry, "Results": Result}
        model = model_map[table_name]
        
        query = session.query(model)
        if table_name == "Races":
            query = query.order_by(model.date.desc())
        
        # Fetch data to DataFrame
        # Use SQL introspection or simple loop
        items = query.all()
        if items:
            data_list = []
            for item in items:
                # simplistic dict conversion
                item_dict = {c.name: getattr(item, c.name) for c in item.__table__.columns}
                data_list.append(item_dict)
            df = pd.DataFrame(data_list)
            st.dataframe(df, use_container_width=True)
            
            # Deletion UI (Specific to Races for simplicity)
            if table_name == "Races":
                st.divider()
                st.warning("レースを削除すると、関連する出走データ(Entries)と結果データ(Results)も削除されます。")
                race_options = {f"{r.date} - {r.name} ({r.id})": r.id for r in items}
                selected_race_key = st.selectbox("削除するレースを選択", list(race_options.keys()))
                
                if st.button("選択したレースを削除", type="primary"):
                    race_id = race_options[selected_race_key]
                    try:
                        # Manually delete dependencies if no cascade
                        session.query(Result).filter(Result.race_id == race_id).delete()
                        session.query(Entry).filter(Entry.race_id == race_id).delete()
                        session.query(Race).filter(Race.id == race_id).delete()
                        session.commit()
                        st.success(f"レース {selected_race_key} を削除しました。")
                        st.rerun()
                    except Exception as e:
                        session.rollback()
                        st.error(f"削除エラー: {e}")
        else:
            st.info("データがありません。")

    with tab2:
        st.subheader("データエクスポート")
        # Export Buttons
        for t_name, t_model in model_map.items():
            items = session.query(t_model).all()
            if items:
                data_list = [{c.name: getattr(item, c.name) for c in item.__table__.columns} for item in items]
                df = pd.DataFrame(data_list)
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label=f"{t_name} (CSV) をダウンロード",
                    data=csv,
                    file_name=f"{t_name.lower()}.csv",
                    mime='text/csv',
                )

        st.divider()
        st.subheader("データインポート")
        st.write("CSVファイルをアップロードしてデータを追加・更新します。")
        
        import_target = st.selectbox("インポート先テーブル", list(model_map.keys()))
        uploaded_file = st.file_uploader("CSVファイルを選択", type=['csv'])
        
        if uploaded_file is not None:
            if st.button("インポート実行"):
                try:
                    import_df = pd.read_csv(uploaded_file)
                    target_model = model_map[import_target]
                    
                    # Convert Date columns if necessary
                    if import_target == "Races" and 'date' in import_df.columns:
                        import_df['date'] = pd.to_datetime(import_df['date']).dt.date
                        
                    # Insert/Update logic
                    success_count = 0
                    for index, row in import_df.iterrows():
                        # Convert row to dict
                        row_dict = row.to_dict()
                        
                        # Clean up NaN values (convert to None)
                        row_dict = {k: (None if pd.isna(v) else v) for k, v in row_dict.items()}
                        
                        # Create instance (using session.merge for upsert)
                        # Note: merge requires primary key to be present in dict
                        instance = target_model(**row_dict)
                        session.merge(instance)
                        success_count += 1
                        
                    session.commit()
                    st.success(f"{success_count} 件のデータを {import_target} にインポートしました。")
                except Exception as e:
                    session.rollback()
                    st.error(f"インポートエラー: {e}")

    with tab3:
        st.subheader("危険な操作")
        if st.button("データベースを全削除 (初期化)", type="primary"):
            confirm = st.checkbox("本当に全てのデータを削除してよろしいですか？")
            if confirm:
                try:
                    from data.database import Base
                    Base.metadata.drop_all(session.get_bind())
                    Base.metadata.create_all(session.get_bind())
                    st.success("データベースを初期化しました。")
                    st.rerun()
                except Exception as e:
                    st.error(f"初期化エラー: {e}")

