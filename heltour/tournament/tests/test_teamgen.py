import random

from django.test import SimpleTestCase

from heltour.tournament import teamgen

# Randomly generated lichess-style usernames, checked to not belong to real lichess accounts.
USERNAMES = """
    mil4oAVsCIt-Tq zOl_rMIFrc Pj5uJS3PB_Ad-ubm7Oa tJ33kXbg-wAxzHLlGbbu wz_M k97SuFA5gPOG
    J1EnPds wdIEPM QHaM NJBVutp0zPHpv4w3jug1 CaGxmuRr_S ml91g teulm yOXrWS6DEJ7
    Paq-vCMakHhU2kL ReoZBJh-r4 Od-8z4avEcARz Fa2fy2d7BNbXOwH5DRhA pZCEAMGMiRsV7FhQ_2ij
    VRy8N5uiUkCfZTr3ER KMvb_4K HqaQ7pp Zp_EXoc2d0 He7mxNTUMbc9O93_e PPKKvgwDTqf2x
    LfAfjO_wJ31isj3Q2mT RaqpXhp67ekNyGU6T8Q Dmyqu_93GG LMdenjbAx_V VtB-Izb6X-I4j5Z_zB7
    lDWrxobG_uL-Ut i_lydU6 HFJvnOa4ebadVw Oy4-dYlr2AVRfg oUOLHVU aZRkJ AIaGDclLKtvW3e9I6
    pomnkbF BXPyfpH94V-lH6uw1fEJ h_Tj-bNBbZ3otex1F cYf94u1pqAeNALs4 fA_1uJqRmo znvJ
    et73Pu8Ov bmTQ CG8cKjeX-Hrt UNrqBffAr fY-O2ZAl IIG4N7-hVBy L-ehC_kB HQYHzsLQMbTyPkA_sY
    jgWH_m-vIqE-hRl T_6KW_9_KalREMi-Kf oFeKF7foiyMiNoYcarM fxXgbu6oaXIhjexvcY5 F_ysu2z-hcB
    p_VXMGW-6 DhCUaelVydw GSJLAF EcLiXYFFy6l8BsbJS jAbLgwTTKXp_7rxaDaO C4aG82T10BlUPojq8F
    vRJ7jd7mUctV2Xna o8uIdS-3P-SWk-hJ fCDQ-quZ7mQWH2G1o Kqo-X3PxsoKLO a_BZEn-dK6
    t3U1_lyxFBG2-Dh Jw7EVMcQZ22TqWV Khxmyv_pZoh2H xYdWZmx LSzs9-7qwLkJ0iYqlM aVLWp
    MIX1C_3wI-Q-uKu Rewb7_g Q0C7fpoBhrkW6C XBGEAdVcLT DIo7UgH_XBtO-EN7 rjbqTVYyp_AJr22LJY
    wZ9YZr_YAtYfif5OfF MPgU3oJdO1-PDO bAij4_1OXus8 tK-6Ez-0_hr-PnT kSFjNarPs9E-ZJ
    EFsV6fJ1_0ZM56_G4x E0FSTU_Vsr lWgWvfI7C5WPeCz-6o Wlojgr_mQZh4 LzqaR4Zm6Mz_FQbyoOLi
    a8nPlBPVBs3r05yr wbCJn665p5tUrQ-gs KPi3skHGq uA-9NRov0CU yT97VBqaZWDNkaZqH Ti-r-E
    guw6h1svb WNUB5V dT_TEXxRTkfuX08 xbItnDIkdTc-nP R_53FPtMCIFK0HFB A13w-gZ_RdN-xYE6PaT
    kdL7g4Vzukoa s6dyh6eYdK0bz Z0aCdZ s42QooqfyleVyifKJm ijUbZR SgrlPkO47mi1
    SLu2ITHHsLW-kJq_rVJt Bw2V9 nIvsUCnE1k nhFU1t QbbH89b mt4ukCJ CE30xE9gQ2am
    Cfy-54knXJpAoDS ZeQ8NhTORvge_c6y yn7prRTp_yV-DEO bBubUM3OP1Ua_x GepKJcxDfYVNUt_5Ap MUVRy
    Dry7 X24q_Xs lp0-I5QET32hdvujTf UF9Vt_9oiaMcZ w2-V3 O237K5Gd-pz5E_QC4X
    OTShef4Q8TFwJiCCPoF c9-wy-h_1mi-rID kenxZqz0Q rehN7yaY CsJB-S lTp-0AztvMk FRAvmJfvprHK
    vTaVKACqy8gQnL-nh5-N EI-mTkUeGbTRueW WGcRq_vVm-2 V4Efz8fK21rME C_i1PYVSwk_pOm lmpLI5OP
    hTf_DL-gpWqa eTkRWQK5 yPTBH5 w2FQ HAtLbSKy-Z0 IkgZ6s-O_E3h-Q2vxPxM cVC1j p_4-LNb
    qzCBI8_Jmn4Wbp_Q EBX1y kSRHPrYmu3C9p-e wu-tkScEgI_K3a LiCh-qWcU8Puvl Kd2nzmxn
    O_TIjlbfXtVqy r88waMbdZccHHr9z ZnlWh1GKWq8Z uSrNkMiW gBl331lzmeGTrd Jkx5nB
    Q32YW-n7_22IIVB GJMp h2OsGBhV1 Tnj_tf14VN_6fKalIMm phoWSkan3xff-40v9lTW
    Zwvaz8KmlFxaXF5Z_Z Gs-HNcI EhTLvlK_qAJBf3dVLjrN yE0SLWU K-EJ PUq3tFyZQ1 Ftfr
    NNAYf9BK8O_Wvyc HqW4 i8ESDBa Kxp_3yNO-d-3e-LZ Zs9xv egnV-q6XuFFc RyXc1WCRPszre
    o6_HfxfgMV EX8bw1kYyiotUfnps HT6n yWzmS_GO_k_iA9xG-lZ rqH1cG ODuFD q4jx53XGA10YE1W_f
    J3RadILdGFBNWMUH sQt2Re HPnL-l_INEn0YEd7M WrtrFNXBUjY-l r8fKVK_z n-q1-cLD1H lGhN
    Y5mVBCbadx59uY ON73PB DmY4e_L1vU8pYv_Xcu grA3_u4L DEjJIoFc L60aVzAy5adaz9rM Uv8j4X0
    GO5kL7JKYUlJVhWK
""".split()


def player(name, rating, preference, registered):
    """A player as Season.export_players() describes them."""
    return {
        "name": name,
        "rating": rating,
        "friends": "",
        "avoid": "",
        "date_created": f"2026-09-01T00:00:{registered:02d}",
        "prefers_alt": preference == "alternate",
        "alt_fine": preference == "either",
        "previous_season_alternate": False,
        "in_slack": True,
    }


def snapshot_players():
    """200 players: friend groups, eight players who paste the same 120-name friend list, and
    a few avoid requests. The pasted lists make the old teamgen take ~10s."""
    rng = random.Random(4545)
    preferences = rng.choices(["full_time", "either", "alternate"], [77, 15, 8], k=200)
    players = [
        player(name, int(rng.gauss(1700, 250)), preference=preference, registered=rng.randrange(60))
        for name, preference in zip(USERNAMES, preferences)
    ]
    grouped = rng.sample(players, 80)
    while grouped:
        group, grouped = grouped[:3], grouped[3:]
        for p in group:
            p["friends"] = ", ".join(q["name"] for q in group if q is not p)
    pasted_list = ", ".join(rng.sample(USERNAMES, 120))
    for p in rng.sample(players, 8):
        p["friends"] = pasted_list
    for p in rng.sample(players, 6):
        p["avoid"] = rng.choice(USERNAMES)
    return players


class MakeLeagueSnapshotTestCase(SimpleTestCase):
    """Pins the exact output of make_league + reduce_variance for a fixed seed, so changes
    meant to keep behaviour (refactors, speedups) can show that they do."""

    def test_output_matches_snapshot(self):
        random.seed(4545)
        league = teamgen.make_league(snapshot_players(), 6, 0.8)
        teams = teamgen.reduce_variance(league["teams"])

        self.assertEqual(
            [" ".join(p.name for p in team.boards) for team in teams], SNAPSHOT_TEAMS
        )
        self.assertEqual(
            [" ".join(p.name for p in board) for board in league["alts_split"]],
            SNAPSHOT_ALTERNATES,
        )


SNAPSHOT_TEAMS = [
    "KMvb_4K hTf_DL-gpWqa Dry7 yE0SLWU gBl331lzmeGTrd E0FSTU_Vsr",
    "VtB-Izb6X-I4j5Z_zB7 CG8cKjeX-Hrt grA3_u4L egnV-q6XuFFc GO5kL7JKYUlJVhWK vRJ7jd7mUctV2Xna",
    "VRy8N5uiUkCfZTr3ER kenxZqz0Q FRAvmJfvprHK lp0-I5QET32hdvujTf tJ33kXbg-wAxzHLlGbbu cVC1j",
    "MPgU3oJdO1-PDO T_6KW_9_KalREMi-Kf GepKJcxDfYVNUt_5Ap ON73PB Bw2V9 cYf94u1pqAeNALs4",
    "MIX1C_3wI-Q-uKu uA-9NRov0CU Kd2nzmxn c9-wy-h_1mi-rID o6_HfxfgMV EcLiXYFFy6l8BsbJS",
    "eTkRWQK5 Dmyqu_93GG yOXrWS6DEJ7 mt4ukCJ et73Pu8Ov IIG4N7-hVBy",
    "Wlojgr_mQZh4 LSzs9-7qwLkJ0iYqlM i_lydU6 He7mxNTUMbc9O93_e HqaQ7pp PUq3tFyZQ1",
    "Rewb7_g AIaGDclLKtvW3e9I6 i8ESDBa kdL7g4Vzukoa WGcRq_vVm-2 yPTBH5",
    "fCDQ-quZ7mQWH2G1o xbItnDIkdTc-nP HT6n HQYHzsLQMbTyPkA_sY o8uIdS-3P-SWk-hJ tK-6Ez-0_hr-PnT",
    "NNAYf9BK8O_Wvyc Ftfr lWgWvfI7C5WPeCz-6o L-ehC_kB KPi3skHGq OTShef4Q8TFwJiCCPoF",
    "DmY4e_L1vU8pYv_Xcu ReoZBJh-r4 LMdenjbAx_V CaGxmuRr_S HFJvnOa4ebadVw WrtrFNXBUjY-l",
    "Pj5uJS3PB_Ad-ubm7Oa p_VXMGW-6 R_53FPtMCIFK0HFB ODuFD Zp_EXoc2d0 O_TIjlbfXtVqy",
    "QHaM r8fKVK_z Ti-r-E X24q_Xs HAtLbSKy-Z0 UNrqBffAr",
    "bAij4_1OXus8 SgrlPkO47mi1 ijUbZR LiCh-qWcU8Puvl LzqaR4Zm6Mz_FQbyoOLi sQt2Re",
    "jgWH_m-vIqE-hRl zOl_rMIFrc Khxmyv_pZoh2H DIo7UgH_XBtO-EN7 Zs9xv oUOLHVU",
    "QbbH89b J1EnPds ZnlWh1GKWq8Z pZCEAMGMiRsV7FhQ_2ij EFsV6fJ1_0ZM56_G4x yn7prRTp_yV-DEO",
    "Q32YW-n7_22IIVB lDWrxobG_uL-Ut LfAfjO_wJ31isj3Q2mT w2FQ fY-O2ZAl kSFjNarPs9E-ZJ",
    "teulm CE30xE9gQ2am xYdWZmx aZRkJ a8nPlBPVBs3r05yr XBGEAdVcLT",
    "jAbLgwTTKXp_7rxaDaO kSRHPrYmu3C9p-e GSJLAF Od-8z4avEcARz lGhN Q0C7fpoBhrkW6C",
    "h_Tj-bNBbZ3otex1F EhTLvlK_qAJBf3dVLjrN WNUB5V ZeQ8NhTORvge_c6y wdIEPM k97SuFA5gPOG",
    "HPnL-l_INEn0YEd7M Y5mVBCbadx59uY bBubUM3OP1Ua_x rehN7yaY yT97VBqaZWDNkaZqH fxXgbu6oaXIhjexvcY5",
    "aVLWp wu-tkScEgI_K3a yWzmS_GO_k_iA9xG-lZ s42QooqfyleVyifKJm Oy4-dYlr2AVRfg s6dyh6eYdK0bz",
    "guw6h1svb Zwvaz8KmlFxaXF5Z_Z n-q1-cLD1H C_i1PYVSwk_pOm NJBVutp0zPHpv4w3jug1 Uv8j4X0",
    "wz_M Kxp_3yNO-d-3e-LZ ml91g a_BZEn-dK6 nIvsUCnE1k q4jx53XGA10YE1W_f",
    "HqW4 Jkx5nB Fa2fy2d7BNbXOwH5DRhA Paq-vCMakHhU2kL rjbqTVYyp_AJr22LJY A13w-gZ_RdN-xYE6PaT",
    "lmpLI5OP DEjJIoFc Cfy-54knXJpAoDS vTaVKACqy8gQnL-nh5-N CsJB-S EBX1y",
]

SNAPSHOT_ALTERNATES = [
    "wbCJn665p5tUrQ-gs h2OsGBhV1 wZ9YZr_YAtYfif5OfF RaqpXhp67ekNyGU6T8Q oFeKF7foiyMiNoYcarM SLu2ITHHsLW-kJq_rVJt Tnj_tf14VN_6fKalIMm",
    "Jw7EVMcQZ22TqWV znvJ dT_TEXxRTkfuX08 F_ysu2z-hcB t3U1_lyxFBG2-Dh p_4-LNb lTp-0AztvMk bmTQ",
    "IkgZ6s-O_E3h-Q2vxPxM Z0aCdZ r88waMbdZccHHr9z uSrNkMiW Kqo-X3PxsoKLO phoWSkan3xff-40v9lTW MUVRy",
    "qzCBI8_Jmn4Wbp_Q nhFU1t PPKKvgwDTqf2x fA_1uJqRmo UF9Vt_9oiaMcZ w2-V3 DhCUaelVydw",
    "V4Efz8fK21rME RyXc1WCRPszre mil4oAVsCIt-Tq K-EJ EI-mTkUeGbTRueW O237K5Gd-pz5E_QC4X L60aVzAy5adaz9rM J3RadILdGFBNWMUH",
    "C4aG82T10BlUPojq8F pomnkbF BXPyfpH94V-lH6uw1fEJ rqH1cG GJMp EX8bw1kYyiotUfnps Gs-HNcI",
]
