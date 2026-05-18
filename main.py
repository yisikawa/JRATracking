import streamlit as st

st.set_page_config(page_title="JRA Tracking App", layout="wide")

st.title("JRA 競馬予測 (Bayesian Inference)")
st.write("左側のサイドバーから機能を選択してください。")

st.sidebar.title("メニュー")
option = st.sidebar.selectbox("機能", ["ダッシュボード", "データ収集", "分析・予測", "今日のレース予測", "データベース管理"])

if option == "ダッシュボード":
    st.header("開催予定のレース")
    st.info("データがありません。データ収集を実行してください。")

elif option == "データ収集":
    st.header("データスクレイピング (netkeiba.com)")
    st.write("netkeibaからレース結果を取得します。")

    tab_date, tab_id, tab_bulk = st.tabs(["日付指定", "レースID / URL指定", "一括収集"])

    with tab_date:
        st.write("指定した日のレース一覧を取得し、全結果をまとめて保存します。")
        target_date = st.date_input("開催日を選択", value=None)

        if st.button("一覧取得 → 全レース保存", key="btn_date"):
            if target_date is None:
                st.warning("日付を選択してください。")
            else:
                from data.scraper import JRAScraper
                from data.database import init_db
                session = init_db()
                scraper = JRAScraper(session)

                with st.spinner("レースID一覧を取得中..."):
                    race_ids = scraper.get_race_ids_by_date(target_date)

                if not race_ids:
                    st.error(
                        "指定日のレースが見つかりませんでした。\n\n"
                        "**考えられる原因:**\n"
                        "- レースが現在進行中 → 結果はレース終了後にnetkeibaへ反映されます\n"
                        "- JRA非開催日 (平日・休止日など)\n"
                        "- 過去の確定済みレースを選んでください（例: 先週の土日）"
                    )
                else:
                    st.info(f"{len(race_ids)} レースを取得します: {race_ids}")
                    progress = st.progress(0)
                    saved, failed = 0, 0
                    for i, race_id in enumerate(race_ids):
                        with st.spinner(f"[{i+1}/{len(race_ids)}] {race_id} を取得中..."):
                            data = scraper.scrape_race_results(race_id)
                            if data:
                                scraper.save_to_db(data)
                                saved += 1
                            else:
                                failed += 1
                        progress.progress((i + 1) / len(race_ids))
                    st.success(f"完了: {saved} レース保存 / {failed} 件失敗")

    with tab_id:
        st.write("12桁のレースIDまたは netkeiba の URL を直接入力します。")
        st.caption("例: `202601060112`　または　`https://db.netkeiba.com/race/202601060112/`")
        race_input = st.text_input("レースID または URL", "202601060112")

        if st.button("データ取得", key="btn_id"):
            from data.scraper import JRAScraper
            from data.database import init_db
            session = init_db()
            scraper = JRAScraper(session)

            with st.spinner("スクレイピング中..."):
                data = scraper.scrape_race_results(race_input)
                if data:
                    st.success(f"取得成功: {data['race'].name}  ({data['race'].location} / {data['race'].course_type}{data['race'].distance}m)")
                    st.dataframe(
                        [{'着順': r.rank, '馬名': e.horse_id, '騎手': e.jockey,
                          'タイム(秒)': r.time_seconds, '単勝': r.odds}
                         for r, e in zip(data['results'], data['entries'])]
                    )
                    scraper.save_to_db(data)
                    st.info("データをデータベースに保存しました。")
                else:
                    st.error("データ取得に失敗しました。レースIDを確認してください（12桁の数字）。")

    with tab_bulk:
        st.write("指定した期間の土日レース結果を自動一括取得します。")

        from datetime import date as _date, timedelta

        years = st.selectbox("収集期間", [1, 2, 3, 4, 5], format_func=lambda x: f"{x}年分", key="bulk_years")

        today = _date.today()
        try:
            start_date = _date(today.year - years, today.month, today.day)
        except ValueError:
            start_date = _date(today.year - years, today.month, 28)

        weekend_dates = []
        d = start_date
        while d <= today:
            if d.weekday() in (5, 6):
                weekend_dates.append(d)
            d += timedelta(days=1)

        st.info(
            f"対象期間: {start_date} 〜 {today}  /  "
            f"土日: {len(weekend_dates)} 日（最大約 {len(weekend_dates) * 12} レース）"
        )

        if st.button("一括収集開始", key="btn_bulk"):
            from data.scraper import JRAScraper
            from data.database import init_db, Race
            session = init_db()
            scraper = JRAScraper(session)

            total_saved = 0
            total_failed = 0
            total_skipped = 0

            date_progress = st.progress(0)
            status_text = st.empty()
            result_text = st.empty()

            for i, target in enumerate(weekend_dates):
                status_text.text(f"[{i+1}/{len(weekend_dates)}] {target} を処理中...")

                race_ids = scraper.get_race_ids_by_date(target)

                for race_id in race_ids:
                    if session.query(Race).filter_by(id=race_id).first():
                        total_skipped += 1
                        continue
                    data = scraper.scrape_race_results(race_id)
                    if data:
                        scraper.save_to_db(data)
                        total_saved += 1
                    else:
                        total_failed += 1

                date_progress.progress((i + 1) / len(weekend_dates))
                result_text.text(
                    f"保存済み: {total_saved} レース / スキップ(取得済み): {total_skipped} / 失敗: {total_failed} 件"
                )

            status_text.text("完了")
            st.success(f"一括収集完了: {total_saved} レース保存 / スキップ: {total_skipped} / 失敗: {total_failed} 件")

elif option == "分析・予測":
    st.header("ベイズ推定モデル")
    st.write("Stanモデルを用いて予測を行います。")

    from data.database import init_db, Result, Entry
    from analysis.predictor import JRAPredictor
    import pandas as pd

    # モデルをセッション間で保持（ページ再描画のたびに再学習しない）
    if 'predictor' not in st.session_state:
        st.session_state.predictor = None
        st.session_state.predictor_summary = None

    train_mode = st.radio(
        "学習モード",
        ['高速 (ADVI)', '標準 (MCMC)', '精密 (MCMC)'],
        horizontal=True,
        help='高速: 数秒〜数分・近似解  /  標準: 数分・chains=2  /  精密: 10分以上・chains=4',
    )
    mode_map = {'高速 (ADVI)': 'advi', '標準 (MCMC)': 'fast', '精密 (MCMC)': 'standard'}

    if st.button("モデル学習 (データ更新)"):
        with st.spinner("データ取得・学習中..."):
            session = init_db()
            results = session.query(Result).all()
            if not results:
                st.warning("学習用データがありません。「データ収集」を行ってください。")
            else:
                data = []
                for r in results:
                    entry = session.query(Entry).filter_by(
                        race_id=r.race_id, horse_id=r.horse_id
                    ).first()
                    if entry:
                        horse_name = entry.horse.name if entry.horse else r.horse_id
                        data.append({
                            'rank':        r.rank,
                            'jockey':      entry.jockey_id or entry.jockey,
                            'jockey_name': entry.jockey,
                            'horse_id':    horse_name,
                        })

                if not data:
                    st.error("有効な学習データが抽出できませんでした。")
                else:
                    df = pd.DataFrame(data)
                    predictor = JRAPredictor()
                    summary = predictor.train(df, mode=mode_map[train_mode])
                    st.session_state.predictor = predictor
                    st.session_state.predictor_summary = summary
                    st.success(
                        f"学習完了 — 騎手 {len(predictor.known_jockeys())} 名 / "
                        f"馬 {len(predictor.known_horses())} 頭"
                    )

    if st.session_state.predictor is not None:
        predictor: JRAPredictor = st.session_state.predictor
        summary: pd.DataFrame   = st.session_state.predictor_summary

        tab_rank, tab_predict = st.tabs(["能力ランキング", "勝率予測"])

        with tab_rank:
            # --- 騎手ランキング ---
            st.subheader("騎手能力ランキング (beta_j)")
            st.write("数値が大きいほど「強い（勝率が高い）」と評価している騎手です。")

            id_to_jockey = {v: k for k, v in predictor.jockey_map.items()
                            if k != predictor.UNKNOWN}
            is_advi = predictor.fit_mode == 'advi'
            beta_j_rows = []
            for i, key in id_to_jockey.items():
                param = f'beta_j[{i}]'
                if param in summary.index:
                    row = summary.loc[param]
                    name = predictor.jockey_display_map.get(key, key)
                    entry = {'騎手': name, '能力値': round(row['Mean'], 3)}
                    if not is_advi:
                        entry.update({'標準偏差': round(row['StdDev'], 3),
                                      '5%': round(row['5%'], 3),
                                      '95%': round(row['95%'], 3),
                                      'R_hat': round(row['R_hat'], 3)})
                    beta_j_rows.append(entry)
            if beta_j_rows:
                jdf = pd.DataFrame(beta_j_rows).set_index('騎手').sort_values('能力値', ascending=False)
                st.dataframe(jdf, use_container_width=True)

            st.divider()

            # --- 馬ランキング ---
            st.subheader("馬能力ランキング (beta_h)")
            st.write("数値が大きいほど「強い」と評価している馬です。")

            id_to_horse = {v: k for k, v in predictor.horse_map.items()
                           if k != predictor.UNKNOWN}
            beta_h_rows = []
            for i, name in id_to_horse.items():
                param = f'beta_h[{i}]'
                if param in summary.index:
                    row = summary.loc[param]
                    entry = {'馬名': name, '能力値': round(row['Mean'], 3)}
                    if not is_advi:
                        entry.update({'標準偏差': round(row['StdDev'], 3),
                                      '5%': round(row['5%'], 3),
                                      '95%': round(row['95%'], 3),
                                      'R_hat': round(row['R_hat'], 3)})
                    beta_h_rows.append(entry)
            if beta_h_rows:
                hdf = pd.DataFrame(beta_h_rows).set_index('馬名').sort_values('能力値', ascending=False)
                st.dataframe(hdf, use_container_width=True)
            else:
                st.info("馬データがありません。")

        with tab_predict:
            st.subheader("出走馬入力 → 勝率予測")
            known_jockeys = set(predictor.known_jockeys())
            known_horses  = set(predictor.known_horses())
            st.caption(
                f"学習済み: 騎手 {len(known_jockeys)} 名 / 馬 {len(known_horses)} 頭。"
                " 未知の名前は平均能力(事前分布の平均)として計算されます。"
            )

            default_df = pd.DataFrame({'騎手': [''] * 6, '馬名': [''] * 6})
            entry_df = st.data_editor(
                default_df,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    '騎手': st.column_config.TextColumn("騎手名", width="medium"),
                    '馬名': st.column_config.TextColumn("馬名",   width="medium"),
                },
            )

            if st.button("予測実行"):
                from data.database import Jockey as JockeyModel
                _session = init_db()
                valid_entries = []
                for _, row in entry_df.iterrows():
                    jockey_input = row['騎手'].strip()
                    horse_input  = row['馬名'].strip()
                    if jockey_input and horse_input:
                        jrec = _session.query(JockeyModel).filter(JockeyModel.name == jockey_input).first()
                        valid_entries.append({
                            'jockey':          jrec.id if jrec else jockey_input,
                            'horse':           horse_input,
                            '_display_jockey': jockey_input,
                        })
                if not valid_entries:
                    st.warning("騎手名と馬名を入力してください。")
                else:
                    with st.spinner("予測計算中..."):
                        prob_win, prob_top3 = predictor.predict(valid_entries)

                    rows = []
                    for e, pw, pt in zip(valid_entries, prob_win, prob_top3):
                        j_ok = e['jockey'] in known_jockeys
                        h_ok = e['horse']  in known_horses
                        if j_ok and h_ok:
                            status = '✓ 既知'
                        elif not j_ok and not h_ok:
                            status = '⚠ 両方不明'
                        elif not j_ok:
                            status = '⚠ 騎手不明'
                        else:
                            status = '⚠ 馬不明'
                        rows.append({
                            '騎手':        e['_display_jockey'],
                            '馬名':        e['horse'],
                            'データ確認':  status,
                            '勝率 (%)':    round(float(pw) * 100, 1),
                            '3着内率 (%)': round(float(pt) * 100, 1),
                        })

                    result_df = (
                        pd.DataFrame(rows)
                        .sort_values('勝率 (%)', ascending=False)
                        .reset_index(drop=True)
                    )
                    st.dataframe(result_df, use_container_width=True)
    else:
        st.info("「モデル学習」ボタンを押して学習を開始してください。")

elif option == "今日のレース予測":
    st.header("今日のレース予測")
    st.write("当日の出馬表を自動取得し、学習済みモデルで勝率を予測します。")

    from data.scraper import JRAScraper, PLACE_CODES
    from data.database import init_db
    import pandas as pd
    from datetime import date as dt_date

    if st.session_state.get('predictor') is None:
        st.warning("先に「分析・予測」→「モデル学習 (データ更新)」を実行してください。")
        st.stop()

    predictor = st.session_state.predictor

    if 'upcoming_race_ids' not in st.session_state:
        st.session_state.upcoming_race_ids = []
    if 'shutuba_cache' not in st.session_state:
        st.session_state.shutuba_cache = {}

    fetch_date = st.date_input("開催日", value=dt_date.today())

    if st.button("レース一覧を取得"):
        session = init_db()
        scraper = JRAScraper(session)
        with st.spinner("レースID取得中..."):
            race_ids = scraper.get_upcoming_race_ids(fetch_date)
        st.session_state.upcoming_race_ids = race_ids
        st.session_state.shutuba_cache = {}
        if race_ids:
            st.success(f"{len(race_ids)} レースを取得しました。")
        else:
            st.error("レースが見つかりません。開催がない日付か、取得に失敗しました。")

    race_ids = st.session_state.upcoming_race_ids
    if not race_ids:
        st.info("「レース一覧を取得」ボタンを押してください。")
        st.stop()

    def race_label(rid):
        venue = PLACE_CODES.get(rid[4:6], rid[4:6])
        return f"{venue} {int(rid[10:12])}R  ({rid})"

    race_options = {race_label(rid): rid for rid in race_ids}
    selected_label = st.selectbox("レースを選択", list(race_options.keys()))
    selected_id = race_options[selected_label]

    if st.button("出馬表取得 → 予測実行"):
        if selected_id not in st.session_state.shutuba_cache:
            session = init_db()
            scraper = JRAScraper(session)
            with st.spinner("出馬表を取得中..."):
                shutuba = scraper.scrape_shutuba(selected_id)
            st.session_state.shutuba_cache[selected_id] = shutuba
        else:
            shutuba = st.session_state.shutuba_cache[selected_id]

        if not shutuba or not shutuba.get('entries'):
            st.warning(
                "出馬表の自動取得ができませんでした。"
                "出馬表がまだ公開されていない場合は、以下に馬名と騎手名を入力して予測できます。"
            )

            from data.database import Jockey as JockeyModel
            manual_df = st.data_editor(
                pd.DataFrame({'馬名': [''] * 16, '騎手': [''] * 16}),
                num_rows='dynamic',
                use_container_width=True,
                column_config={
                    '馬名': st.column_config.TextColumn('馬名', width='medium'),
                    '騎手': st.column_config.TextColumn('騎手名', width='medium'),
                },
                key='manual_shutuba_editor',
            )

            if st.button('予測実行', key='btn_manual_today'):
                _sess = init_db()
                manual_entries = []
                for i, row in manual_df.iterrows():
                    horse = row['馬名'].strip()
                    jname = row['騎手'].strip()
                    if horse and jname:
                        jrec = _sess.query(JockeyModel).filter(JockeyModel.name == jname).first()
                        manual_entries.append({
                            'horse_name':      horse,
                            'jockey':          jrec.id if jrec else jname,
                            '_display_jockey': jname,
                            'horse_number':    i + 1,
                        })

                if not manual_entries:
                    st.warning('馬名と騎手名を入力してください。')
                else:
                    pred_input = [{'jockey': e['jockey'], 'horse': e['horse_name']} for e in manual_entries]
                    with st.spinner('予測計算中...'):
                        prob_win, prob_top3 = predictor.predict(pred_input)

                    rows = []
                    for e, pi, pw, pt in zip(manual_entries, pred_input, prob_win, prob_top3):
                        j_ok = pi['jockey']    in known_jockeys
                        h_ok = e['horse_name'] in known_horses
                        if   j_ok and h_ok:         status = '✓'
                        elif not j_ok and not h_ok: status = '⚠ 両方不明'
                        elif not j_ok:              status = '⚠ 騎手不明'
                        else:                       status = '⚠ 馬不明'
                        rows.append({
                            '馬番':        e['horse_number'],
                            '馬名':        e['horse_name'],
                            '騎手':        e['_display_jockey'],
                            'データ確認':  status,
                            '勝率 (%)':    round(float(pw) * 100, 1),
                            '3着内率 (%)': round(float(pt) * 100, 1),
                        })

                    result_df = pd.DataFrame(rows).sort_values('勝率 (%)', ascending=False).reset_index(drop=True)
                    st.dataframe(result_df, use_container_width=True)

                    unknown_count = sum(1 for r in rows if '不明' in r['データ確認'])
                    if unknown_count:
                        st.caption(
                            f"⚠ {unknown_count} 頭の騎手または馬が学習データに含まれていません。"
                            " より多くのレースデータを収集してから再学習すると精度が上がります。"
                        )

            st.stop()

        entries = shutuba['entries']
        loc      = shutuba.get('location', '')
        ctype    = shutuba.get('course_type', '')
        dist     = shutuba.get('distance', 0)
        weather  = shutuba.get('weather', '')
        rname    = shutuba.get('race_name', selected_id)

        st.subheader(f"{rname}")
        meta_parts = [loc, f"{ctype}{dist}m" if dist else "", weather]
        st.caption("  /  ".join(p for p in meta_parts if p))

        known_jockeys = set(predictor.known_jockeys())
        known_horses  = set(predictor.known_horses())

        pred_input = [
            {'jockey': e.get('jockey_id') or e['jockey'], 'horse': e['horse_name']}
            for e in entries
        ]

        with st.spinner("予測計算中..."):
            prob_win, prob_top3 = predictor.predict(pred_input)

        rows = []
        for e, pi, pw, pt in zip(entries, pred_input, prob_win, prob_top3):
            j_ok = pi['jockey']    in known_jockeys
            h_ok = e['horse_name'] in known_horses
            if   j_ok and h_ok:        status = '✓'
            elif not j_ok and not h_ok: status = '⚠ 両方不明'
            elif not j_ok:              status = '⚠ 騎手不明'
            else:                       status = '⚠ 馬不明'

            rows.append({
                '枠':         e['bracket_number'],
                '馬番':       e['horse_number'],
                '馬名':       e['horse_name'],
                '性齢':       f"{e['sex']}{e['age']}",
                '斤量':       e['weight'],
                '騎手':       e['jockey'],
                '調教師':     e['trainer'],
                'データ確認': status,
                '勝率 (%)':   round(float(pw) * 100, 1),
                '3着内率 (%)': round(float(pt) * 100, 1),
            })

        result_df = (
            pd.DataFrame(rows)
            .sort_values('勝率 (%)', ascending=False)
            .reset_index(drop=True)
        )
        st.dataframe(result_df, use_container_width=True)

        unknown_count = sum(1 for r in rows if '不明' in r['データ確認'])
        if unknown_count:
            st.caption(
                f"⚠ {unknown_count} 頭の騎手または馬が学習データに含まれていません。"
                " より多くのレースデータを収集してから再学習すると精度が上がります。"
            )

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
                        race_obj = session.query(Race).get(race_id)
                        if race_obj:
                            session.delete(race_obj)  # cascade で Entry/Result も自動削除
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

