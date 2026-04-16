"""
Sentinela Ecosystem - Auditoria de Precisão Máxima (VERSÃO INTEGRAL)
Foco: PGDAS Anexos I/III, Continuidade, Input Manual, Espécies 36/42 e Matriosca ZIP
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas decimais para bater com o simulador da Receita Federal
getcontext().prec = 60 

# ─── BANCO DE DIRETRIZES FISCAIS (BASE DE DATA) ────────────────────────────
DIRETRIZES_FISCAIS = {
    "08399950000142": {
        "nome": "LOGUS COMERCIO DE FERRAMENTAS",
        "anexo_i": {"st_icms": True},  
        "anexo_iii": {"locacao": True}, 
    }
}

# ─── TABELAS DE PARTILHA (REGRAS OFICIAIS PGDAS) ───────────────────────────
PARTILHA_ANEXO_I = {
    1: {'icms': Decimal("0.34")}, 2: {'icms': Decimal("0.34")},
    3: {'icms': Decimal("0.335")}, 4: {'icms': Decimal("0.335")},
    5: {'icms': Decimal("0.335")}, 6: {'icms': Decimal("0.00")}
}

PARTILHA_ANEXO_III = {
    1: {'iss': Decimal("0.32")}, 2: {'iss': Decimal("0.32")},
    3: {'iss': Decimal("0.325")}, 4: {'iss': Decimal("0.325")},
    5: {'iss': Decimal("0.335")}, 6: {'iss': Decimal("0.00")}
}

TABELA_ANEXO_I = [(1, 0, 180000, 0.04, 0), (2, 180000.01, 360000, 0.073, 5940), (3, 360000.01, 720000, 0.095, 13860), (4, 720000.01, 1800000, 0.107, 22500), (5, 1800000.01, 3600000, 0.143, 87300), (6, 3600000.01, 4800000, 0.19, 378000)]
TABELA_ANEXO_III = [(1, 0, 180000, 0.06, 0), (2, 180000.01, 360000, 0.112, 9360), (3, 360000.01, 720000, 0.135, 17640), (4, 720000.01, 1800000, 0.16, 35640), (5, 1800000.01, 3600000, 0.21, 125640), (6, 3600000.01, 4800000, 0.33, 648000)]

CFOPS_SERVICO = {"5933", "6933", "5124", "6124"}
CFOPS_VENDA = {"5101", "5102", "5103", "5105", "5106", "5107", "5108", "5401", "5403", "5405", "6101", "6102", "6401", "6403", "6404"}
CFOPS_DEVOL = {"1201", "1202", "1411", "2201", "2202", "2411", "5201", "5202", "5411", "6201", "6202", "6411"}

# ─── FUNÇÕES DE FORMATO ─────────────────────────────────────────────────────

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fmt_aliq(v): return f"{(v * 100):,.4f}".replace(".", ",") + "%"
def limpar_cnpj(c): return re.sub(r'\D', '', str(c))

# ─── PROCESSAMENTO XML ─────────────────────────────────────────────────────

def extrair_dados_detalhados(conteudo, cnpj_alvo, radical_grupo):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        ide = inf.find(f"{ns}ide")
        n_nota, serie, mod_xml, tp_nf = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text, ide.find(f"{ns}tpNF").text
        especie = "36" if mod_xml == "55" else "42" if mod_xml == "65" else mod_xml

        for det in inf.findall(f"{ns}det"):
            prod, impo = det.find(f"{ns}prod"), det.find(f"{ns}imposto")
            cfop = prod.find(f"{ns}CFOP").text.replace(".", "")
            
            icms_node = impo.find(f".//{ns}ICMS")
            possui_st = False
            if icms_node is not None:
                csosn = icms_node.find(f".//{ns}CSOSN")
                if csosn is not None and csosn.text in ["201", "202", "203", "500"]: possui_st = True

            v_p = Decimal(prod.find(f"{ns}vProd").text)
            v_d = Decimal(prod.find(f"{ns}vDesc").text) if prod.find(f"{ns}vDesc") is not None else Decimal("0")
            v_o = Decimal(prod.find(f"{ns}vOutro").text) if prod.find(f"{ns}vOutro") is not None else Decimal("0")
            v_f = Decimal(prod.find(f"{ns}vFrete").text) if prod.find(f"{ns}vFrete") is not None else Decimal("0")
            base_item = (v_p - v_d + v_o + v_f).quantize(Decimal("0.01"), ROUND_HALF_UP)
            
            categoria = "OUTROS"
            if emit_cnpj == cnpj_alvo and tp_nf == "1":
                if cfop in CFOPS_VENDA or cfop in CFOPS_SERVICO: categoria = "RECEITA BRUTA"
            elif cfop in CFOPS_DEVOL:
                if (emit_cnpj.startswith(radical_grupo) and tp_nf == "0") or (dest_cnpj.startswith(radical_grupo) and tp_nf == "1"):
                    categoria = "DEVOLUÇÃO VENDA"

            anexo = "ANEXO III" if cfop in CFOPS_SERVICO else "ANEXO I"

            regs.append({
                "Unidade_CNPJ": emit_cnpj if emit_cnpj.startswith(radical_grupo) else dest_cnpj,
                "Nota": n_nota, "Espécie": especie, "Série": serie, "CFOP": cfop, "ST": possui_st, 
                "Anexo": anexo, "Base_DAS": base_item, "Categoria": categoria, "Chave": chave
            })
    except: pass
    return regs

def extrair_canceladas(conteudo):
    ch_canc = set()
    try:
        root = ET.fromstring(conteudo.lstrip()); ns = "{http://www.portalfiscal.inf.br/nfe}"
        for ev in root.findall(f".//{ns}infEvento"):
            if ev.find(f"{ns}tpEvento").text == "110111": ch_canc.add(ev.find(f"{ns}chNFe").text)
        inf = root.find(f".//{ns}infNFe")
        if inf is not None: ch_canc.add(inf.attrib.get('Id', '')[3:])
    except: pass
    return ch_canc

def processar_recursivo(arquivo_bytes, func, **kwargs):
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for n in z.namelist():
                c = z.read(n)
                if n.lower().endswith('.zip'): results.extend(processar_recursivo(c, func, **kwargs))
                elif n.lower().endswith('.xml'):
                    res = func(c, **kwargs)
                    if isinstance(res, list): results.extend(res)
                    else: results.append(res)
    except:
        res = func(arquivo_bytes, **kwargs)
        if isinstance(res, list): results.extend(res)
        elif isinstance(res, set): results.append(res)
        else: results.append(res)
    return results

# ─── MOTOR DE CÁLCULO PGDAS ──────────────────────────────────────────────────

def calcular_aliq_efetiva(anexo, possui_st, rb12, st_i, loc_iii):
    tab, partilha = (TABELA_ANEXO_I, PARTILHA_ANEXO_I) if anexo == "ANEXO I" else (TABELA_ANEXO_III, PARTILHA_ANEXO_III)
    faixa = tab[0]; f_idx = 1
    for f in tab:
        if rb12 <= f[2]: faixa = f; f_idx = f[0]; break
        faixa = f; f_idx = f[0]
    
    ae_bruta = ((rb12 * Decimal(str(faixa[3]))) - Decimal(str(faixa[4]))) / rb12
    p = partilha[f_idx]
    red = Decimal("0")
    if anexo == "ANEXO I" and st_i and possui_st: red = p.get('icms', 0)
    elif anexo == "ANEXO III" and loc_iii: red = p.get('iss', 0)
    return ae_bruta * (Decimal("1") - red)

# ─── INTERFACE STREAMLIT ───────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Sentinela Group - Auditoria Total", layout="wide")
    st.markdown("""<style> h1, h2, h3 { color: #d81b60; font-weight: 800; } .stMetric { background: #fff; border-left: 5px solid #d81b60; padding: 10px; border-radius: 5px; } </style>""", unsafe_allow_html=True)

    st.title("🛡️ Sentinela Ecosystem - Auditoria Fiel")
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Perfil Empresa")
        cnpj_input = st.text_input("CNPJ Alvo", key=f"c_{st.session_state.reset_key}")
        cnpj_alvo = limpar_cnpj(cnpj_input); rad = cnpj_alvo[:8] if cnpj_alvo else ""
        rbt12_raw = st.text_input("RBT12 Total", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        st.header("🧱 Diretrizes")
        config = DIRETRIZES_FISCAIS.get(cnpj_alvo, {"anexo_i": {"st_icms": True}, "anexo_iii": {"locacao": True}})
        st_i = st.checkbox("Anexo I: Possui ST?", value=config["anexo_i"]["st_icms"])
        loc_iii = st.checkbox("Anexo III: Locação?", value=config["anexo_iii"]["locacao"])
        
        st.subheader("💰 Locação Manual")
        val_loc_raw = st.text_input("Valor Manual de Locação (R$)", value="0,00", key=f"loc_{st.session_state.reset_key}")
        v_loc_manual = Decimal(val_loc_raw.replace(".", "").replace(",", "."))
        
        if st.button("🗑️ Resetar Tudo"): st.session_state.reset_key += 1; st.rerun()

    c1, c2 = st.columns(2)
    with c1: f_norm = st.file_uploader("Movimentação ZIP/XML", accept_multiple_files=True)
    with c2: f_canc = st.file_uploader("Canceladas ZIP/XML", accept_multiple_files=True)

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_alvo or rbt12 == 0: st.error("Faltam dados essenciais."); return
        
        canc = set()
        for f in f_canc:
            res_c = processar_recursivo(f.read(), extrair_canceladas)
            for item in res_c:
                if isinstance(item, set): canc.update(item)
                else: canc.add(item)
        
        regs = []
        for f in f_norm: regs.extend(processar_recursivo(f.read(), extrair_dados_detalhados, cnpj_alvo=cnpj_alvo, radical_grupo=rad))
        
        if regs:
            df = pd.DataFrame(regs).drop_duplicates(subset=['Chave', 'Base_DAS', 'CFOP'])
            df['Cancelada'] = df['Chave'].isin(canc)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), 'Base_DAS'] = Decimal("0")

            # ─── RESUMO DE CONTINUIDADE (RESTAURADO) ───
            st.subheader("📊 Resumo de Continuidade")
            df_cont = df[~df['Cancelada']].copy()
            if not df_cont.empty:
                res_cont = df_cont.groupby(['Unidade_CNPJ', 'Série']).agg(
                    Primeira_Nota=('Nota', 'min'),
                    Ultima_Nota=('Nota', 'max'),
                    Qtd_Lida=('Nota', 'nunique')
                ).reset_index()
                st.table(res_cont)

            df_f = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            if v_loc_manual > 0:
                loc_row = pd.DataFrame([{"Unidade_CNPJ": cnpj_alvo, "Nota": 0, "Espécie": "MANUAL", "Série": "LOC", "CFOP": "LOC", "ST": False, "Anexo": "ANEXO III", "Base_DAS": v_loc_manual, "Categoria": "RECEITA BRUTA", "Cancelada": False}])
                df_f = pd.concat([df_f, loc_row], ignore_index=True)

            if not df_f.empty:
                def calc_row(row):
                    af = calcular_aliq_efetiva(row['Anexo'], row['ST'], rbt12, st_i, loc_iii)
                    mult = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                    das = ((row['Base_DAS'] * mult) * af).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    return af, das

                res_f = df_f.apply(calc_row, axis=1, result_type='expand')
                df_f['Aliq_Final'], df_f['DAS_Valor'] = res_f[0], res_f[1]

                st.subheader("📑 Memorial Analítico por Espécie")
                for esp in sorted(df_f['Espécie'].unique()):
                    with st.expander(f"📌 Espécie {esp}", expanded=True):
                        df_esp = df_f[df_f['Espécie'] == esp].copy()
                        resumo = df_esp.groupby(['Anexo', 'CFOP', 'ST']).agg({'Base_DAS': 'sum', 'DAS_Valor': 'sum'}).reset_index()
                        resumo['Alíquota'] = resumo.apply(lambda r: calcular_aliq_efetiva(r['Anexo'], r['ST'], rbt12, st_i, loc_iii), axis=1).apply(fmt_aliq)
                        resumo['Faturamento'] = resumo['Base_DAS'].apply(fmt_br); resumo['DAS'] = resumo['DAS_Valor'].apply(fmt_br)
                        st.table(resumo[['Anexo', 'CFOP', 'ST', 'Alíquota', 'Faturamento', 'DAS']])

                st.subheader("🧱 Consolidação por Anexo")
                res_an = df_f.groupby('Anexo').agg({'Base_DAS': 'sum', 'DAS_Valor': 'sum'}).reset_index()
                res_an['Base Líquida'] = res_an['Base_DAS'].apply(fmt_br); res_an['Imposto Total'] = res_an['DAS_Valor'].apply(fmt_br)
                st.table(res_an[['Anexo', 'Base Líquida', 'Imposto Total']])

                m1, m2, m3 = st.columns(3)
                m1.metric("Bruto Auditado", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_DAS'].sum())}")
                m2.metric("(-) Devoluções", f"R$ {fmt_br(abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_DAS'].sum()))}")
                m3.metric("Total DAS", f"R$ {fmt_br(df_f['DAS_Valor'].sum())}")

            st.subheader("📋 Auditoria de Itens")
            df_view = df.copy(); df_view['Base_DAS'] = df_view['Base_DAS'].apply(fmt_br)
            st.dataframe(df_view[['Unidade_CNPJ', 'Nota', 'Série', 'Espécie', 'CFOP', 'ST', 'Anexo', 'Base_DAS', 'Cancelada']], use_container_width=True)
        else: st.error("Nada processável.")

if __name__ == "__main__": main()
