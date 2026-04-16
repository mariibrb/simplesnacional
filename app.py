"""
Sentinela Ecosystem - Auditoria Universal Rihanna Mode (VERSÃO PARAMETRIZÁVEL)
Foco: PGDAS Configurável (ST, Locação, Partilha Dinâmica), Matriz/Filiais e Matriosca
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão interna de alta fidelidade
getcontext().prec = 60 

# ─── TABELAS DE PARTILHA (REGRAS OFICIAIS DO COMITÊ GESTOR) ────────────────
PARTILHA_ANEXO_I = {
    1: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.415"), 'icms': Decimal("0.34")},
    2: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.415"), 'icms': Decimal("0.34")},
    3: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
    4: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
    5: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
    6: {'irpj': Decimal("0.135"), 'csll': Decimal("0.10"), 'cofins': Decimal("0.2827"), 'pis': Decimal("0.0613"), 'cpp': Decimal("0.421"), 'icms': Decimal("0.00")},
}

PARTILHA_ANEXO_II = {
    1: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1151"), 'pis': Decimal("0.0249"), 'cpp': Decimal("0.375"), 'ipi': Decimal("0.075"), 'icms': Decimal("0.32")},
    2: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1151"), 'pis': Decimal("0.0249"), 'cpp': Decimal("0.375"), 'ipi': Decimal("0.075"), 'icms': Decimal("0.32")},
    3: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1151"), 'pis': Decimal("0.0249"), 'cpp': Decimal("0.375"), 'ipi': Decimal("0.075"), 'icms': Decimal("0.32")},
    4: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1151"), 'pis': Decimal("0.0249"), 'cpp': Decimal("0.375"), 'ipi': Decimal("0.075"), 'icms': Decimal("0.32")},
    5: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1151"), 'pis': Decimal("0.0249"), 'cpp': Decimal("0.375"), 'ipi': Decimal("0.075"), 'icms': Decimal("0.32")},
    6: {'irpj': Decimal("0.085"), 'csll': Decimal("0.075"), 'cofins': Decimal("0.2096"), 'pis': Decimal("0.0454"), 'cpp': Decimal("0.235"), 'ipi': Decimal("0.35"), 'icms': Decimal("0.00")},
}

PARTILHA_ANEXO_III = {
    1: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    2: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    3: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    4: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    5: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    6: {'irpj': Decimal("0.35"), 'csll': Decimal("0.12"), 'cofins': Decimal("0.1282"), 'pis': Decimal("0.0278"), 'cpp': Decimal("0.374"), 'iss': Decimal("0.00")},
}

# Faixas de Alíquota Nominal e Dedução
TABELA_ANEXO_I = [(1, 0, 180000, 0.04, 0), (2, 180000.01, 360000, 0.073, 5940), (3, 360000.01, 720000, 0.095, 13860), (4, 720000.01, 1800000, 0.107, 22500), (5, 1800000.01, 3600000, 0.143, 87300), (6, 3600000.01, 4800000, 0.19, 378000)]
TABELA_ANEXO_II = [(1, 0, 180000, 0.045, 0), (2, 180000.01, 360000, 0.078, 5940), (3, 360000.01, 720000, 0.10, 13860), (4, 720000.01, 1800000, 0.112, 22500), (5, 1800000.01, 3600000, 0.147, 85500), (6, 3600000.01, 4800000, 0.30, 720000)]
TABELA_ANEXO_III = [(1, 0, 180000, 0.06, 0), (2, 180000.01, 360000, 0.112, 9360), (3, 360000.01, 720000, 0.135, 17640), (4, 720000.01, 1800000, 0.16, 35640), (5, 1800000.01, 3600000, 0.21, 125640), (6, 3600000.01, 4800000, 0.33, 648000)]

CFOPS_INDUSTRIA = {"5101", "6101", "5401", "6401", "5103", "5104"}
CFOPS_SERVICO = {"5933", "6933", "5124", "6124"}
CFOPS_VENDA_GERAL = {"5101", "5102", "5103", "5105", "5106", "5107", "5108", "6101", "6102", "6103", "6105", "6106", "6107", "6108", "5401", "5403", "5405", "6401", "6403", "6404"}
CFOPS_DEVOL_PROPRIA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_DEVOL_TERCEIRO = {"5201", "5202", "5411", "6201", "6202", "6411"}

# ─── FUNÇÕES DE FORMATAÇÃO PT-BR ─────────────────────────────────────────────

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fmt_aliq(v): return f"{(v * 100):,.13f}".replace(".", ",") + "%"
def limpar_cnpj(c): return re.sub(r'\D', '', str(c))

# ─── PROCESSAMENTO XML POR ITEM ─────────────────────────────────────────────

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
            
            # Detecção ST por CSOSN
            icms_node = impo.find(f".//{ns}ICMS")
            possui_st = False
            if icms_node is not None:
                csosn_node = icms_node.find(f".//{ns}CSOSN")
                if csosn_node is not None and csosn_node.text in ["201", "202", "203", "500"]: possui_st = True

            v_p = Decimal(prod.find(f"{ns}vProd").text)
            v_d = Decimal(prod.find(f"{ns}vDesc").text) if prod.find(f"{ns}vDesc") is not None else Decimal("0")
            v_o = Decimal(prod.find(f"{ns}vOutro").text) if prod.find(f"{ns}vOutro") is not None else Decimal("0")
            v_f = Decimal(prod.find(f"{ns}vFrete").text) if prod.find(f"{ns}vFrete") is not None else Decimal("0")
            
            base_item = (v_p - v_d + v_o + v_f).quantize(Decimal("0.01"), ROUND_HALF_UP)
            
            categoria = "OUTROS"
            if emit_cnpj == cnpj_alvo and tp_nf == "1":
                if cfop in CFOPS_VENDA_GERAL or cfop in CFOPS_SERVICO: categoria = "RECEITA BRUTA"
            elif emit_cnpj.startswith(radical_grupo) and tp_nf == "0" and cfop in CFOPS_DEVOL_PROPRIA:
                categoria = "DEVOLUÇÃO VENDA"
            elif dest_cnpj.startswith(radical_grupo) and tp_nf == "1" and cfop in CFOPS_DEVOL_TERCEIRO:
                categoria = "DEVOLUÇÃO VENDA"

            if cfop in CFOPS_SERVICO or especie == "42": anexo = "ANEXO III"
            elif cfop in CFOPS_INDUSTRIA: anexo = "ANEXO II"
            else: anexo = "ANEXO I"

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
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        for ev in root.findall(f".//{ns}infEvento"):
            if ev.find(f"{ns}tpEvento").text == "110111": ch_canc.add(ev.find(f"{ns}chNFe").text)
        inf = root.find(f".//{ns}infNFe")
        if inf is not None: ch_canc.add(inf.attrib.get('Id', '')[3:])
    except: pass
    return ch_canc

# ─── MOTOR MATRIOSCA RECURSIVO ──────────────────────────────────────────────

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

# ─── INTERFACE STREAMLIT ─────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Sentinela Universal - Auditoria", layout="wide")
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
            html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
            .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
            h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
            .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
            .stButton>button { background-color: #d81b60; color: white; border-radius: 20px; font-weight: 600; width: 100%; }
            .stTable { background-color: rgba(255, 255, 255, 0.4); border-radius: 10px; }
            .stExpander { background-color: rgba(255, 255, 255, 0.2); border-radius: 10px; border: none; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Sentinela Ecosystem - Auditoria Universal")
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Perfil da Empresa")
        cnpj_input = st.text_input("CNPJ Alvo (Emissão Própria)", key=f"c_{st.session_state.reset_key}")
        cnpj_alvo = limpar_cnpj(cnpj_input)
        radical = cnpj_alvo[:8] if cnpj_alvo else ""
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Total", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        st.header("📋 Regras de Partilha")
        st.write("Ajuste conforme o extrato:")
        st_anexo_i = st.checkbox("Anexo I: Possui ST de ICMS?", value=True)
        locacao_bens = st.checkbox("Anexo III: É Locação? (Zera ISS)", value=False)
        st_anexo_ii = st.checkbox("Anexo II: Possui ST de ICMS?", value=True)
        
        if st.button("🗑️ Resetar Tudo"): st.session_state.reset_key += 1; st.rerun()

    c1, c2 = st.columns(2)
    with c1: f_norm = st.file_uploader("Movimentação (XML/ZIP)", accept_multiple_files=True, key=f"u1_{st.session_state.reset_key}")
    with c2: f_canc = st.file_uploader("Canceladas (XML/ZIP)", accept_multiple_files=True, key=f"u2_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_alvo or rbt12 == 0: st.error("Faltam dados essenciais."); return
        canc = set()
        for f in f_canc:
            res_c = processar_recursivo(f.read(), extrair_canceladas)
            for item in res_c:
                if isinstance(item, set): canc.update(item)
                else: canc.add(item)
        
        regs_raw = []
        for f in f_norm: regs_raw.extend(processar_recursivo(f.read(), extrair_dados_detalhados, cnpj_alvo=cnpj_alvo, radical_grupo=radical))
        
        if regs_raw:
            df = pd.DataFrame(regs_raw)
            df = df.drop_duplicates(subset=['Chave', 'Base_DAS', 'CFOP'], keep='first')
            df['Cancelada'] = df['Chave'].isin(canc)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), 'Base_DAS'] = Decimal("0")

            def calc_ae_universal(anexo, st_item, rb_total):
                if anexo == "ANEXO I": tab, p_map = TABELA_ANEXO_I, PARTILHA_ANEXO_I
                elif anexo == "ANEXO II": tab, p_map = TABELA_ANEXO_II, PARTILHA_ANEXO_II
                else: tab, p_map = TABELA_ANEXO_III, PARTILHA_ANEXO_III
                
                faixa = tab[0]; f_idx = 1
                for f in tab:
                    if rb_total <= f[2]: faixa = f; f_idx = f[0]; break
                    faixa = f; f_idx = f[0]
                
                ae = ((rb_total * Decimal(str(faixa[3]))) - Decimal(str(faixa[4]))) / rb_total
                
                # APLICAÇÃO DAS REGRAS DINÂMICAS DA SIDEBAR
                p = p_map[f_idx]
                deducao = Decimal("0")
                if anexo == "ANEXO I" and st_anexo_i and st_item: deducao += p.get('icms', 0)
                if anexo == "ANEXO II" and st_anexo_ii and st_item: deducao += p.get('icms', 0)
                if anexo == "ANEXO III" and locacao_bens: deducao += p.get('iss', 0)
                
                return ae * (Decimal("1") - deducao)

            df_f = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            if not df_f.empty:
                aliqs = { f"{a}_{s}": calc_ae_universal(a, s, rbt12) for a in ["ANEXO I", "ANEXO II", "ANEXO III"] for s in [True, False] }
                def aplicar(row):
                    af = aliqs[f"{row['Anexo']}_{row['ST']}"]
                    mult = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                    base = (row['Base_DAS'] * mult).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    return af, (base * af).quantize(Decimal("0.01"), ROUND_HALF_UP)

                res = df_f.apply(aplicar, axis=1, result_type='expand')
                df_f['Aliq_F'], df_f['DAS'] = res[0], res[1]

                st.subheader("📑 Memorial Analítico por Espécie")
                for esp in sorted(df_f['Espécie'].unique()):
                    label = f"Espécie {esp} ({'NF-e' if esp=='36' else 'NFC-e' if esp=='42' else 'Outros'})"
                    with st.expander(f"📌 {label}", expanded=True):
                        df_esp = df_f[df_f['Espécie'] == esp].copy()
                        resumo = df_esp.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'Base_DAS': 'sum', 'DAS': 'sum'}).reset_index()
                        resumo['Aliq (%)'] = df_esp.groupby(['Anexo', 'CFOP', 'ST', 'Categoria'])['Aliq_F'].first().values
                        resumo['Aliq (%)'] = resumo['Aliq (%)'].apply(fmt_aliq)
                        resumo['Base PGDAS'] = resumo['Base_DAS'].apply(fmt_br)
                        resumo['Imposto DAS'] = resumo['DAS'].apply(fmt_br)
                        st.table(resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq (%)', 'Base PGDAS', 'Imposto DAS']])

                st.subheader("🧱 Consolidação por Anexo")
                res_an = df_f.groupby('Anexo').agg({'Base_DAS': 'sum', 'DAS': 'sum'}).reset_index()
                res_an['Base Líquida'] = res_an['Base_DAS'].apply(fmt_br)
                res_an['Total DAS'] = res_an['DAS'].apply(fmt_br)
                st.table(res_an[['Anexo', 'Base Líquida', 'Total DAS']])

                m1, m2, m3 = st.columns(3)
                m1.metric("Faturamento Líquido", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_DAS'].sum())}")
                m2.metric("(-) Devoluções", f"R$ {fmt_br(abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_DAS'].sum()))}")
                m3.metric("Total DAS Grupo", f"R$ {fmt_br(df_f['DAS'].sum())}")

            st.subheader("📋 Auditoria de Itens")
            df_view = df.copy()
            df_view['Base_DAS'] = df_view['Base_DAS'].apply(fmt_br)
            st.dataframe(df_view[['Unidade_CNPJ', 'Nota', 'Espécie', 'Série', 'CFOP', 'ST', 'Anexo', 'Categoria', 'Base_DAS', 'Cancelada']], use_container_width=True)
        else: st.error("Nenhuma nota processável encontrada.")

if __name__ == "__main__": main()
