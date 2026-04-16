"""
Sentinela Ecosystem - Auditoria Universal Rihanna Mode (VERSÃO TOTAL E ÍNTEGRA)
Foco: Rigor Fiscal, Decomposição de Alíquotas, Continuidade 55/65 e Matriosca ZIP
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão absoluta para bater com as 13 casas decimais do simulador da Receita
getcontext().prec = 60 

# ─── BANCO DE DIRETRIZES FISCAIS (CADASTRO POR CNPJ) ───────────────────────
DIRETRIZES_EMPRESAS = {
    "08399950000142": {
        "nome": "LOGUS COMERCIO DE FERRAMENTAS",
        "anexo_i_st": True,   
        "anexo_iii_regra": "CHEIA", # Alíquota de 7,28% conforme extrato
    }
}

# ─── TABELAS DE PARTILHA DETALHADA (PERCENTUAIS POR TRIBUTO) ───────────────
PARTILHA_ANEXO_I = {
    1: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.415"), 'icms': Decimal("0.34")},
    2: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.415"), 'icms': Decimal("0.34")},
    3: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
    4: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
    5: {'irpj': Decimal("0.055"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1274"), 'pis': Decimal("0.0276"), 'cpp': Decimal("0.42"), 'icms': Decimal("0.335")},
}

PARTILHA_ANEXO_III = {
    1: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    2: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.32")},
    3: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.325")},
    4: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.325")},
    5: {'irpj': Decimal("0.04"), 'csll': Decimal("0.035"), 'cofins': Decimal("0.1405"), 'pis': Decimal("0.0305"), 'cpp': Decimal("0.434"), 'iss': Decimal("0.335")},
}

TABELA_ANEXO_I = [(1, 0, 180000, 0.04, 0), (2, 180000.01, 360000, 0.073, 5940), (3, 360000.01, 720000, 0.095, 13860), (4, 720000.01, 1800000, 0.107, 22500), (5, 1800000.01, 3600000, 0.143, 87300)]
TABELA_ANEXO_III = [(1, 0, 180000, 0.06, 0), (2, 180000.01, 360000, 0.112, 9360), (3, 360000.01, 720000, 0.135, 17640), (4, 720000.01, 1800000, 0.16, 35640), (5, 1800000.01, 3600000, 0.21, 125640)]

CFOPS_SERVICO = {"5933", "6933", "5124", "6124"}
CFOPS_VENDA = {"5101", "5102", "5103", "5105", "5106", "5107", "5108", "5401", "5403", "5405", "6101", "6102", "6401", "6403", "6404"}

# ─── FUNÇÕES DE SUPORTE (FORMATAÇÃO PT-BR) ───────────────────────────────────

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fmt_aliq(v): return f"{(v * 100):,.13f}".replace(".", ",") + "%"
def limpar_cnpj(c): return re.sub(r'\D', '', str(c))

# ─── PROCESSAMENTO XML (VARRRE TODOS OS ITENS E TOTAIS) ─────────────────────

def extrair_dados_detalhados(conteudo, cnpj_alvo):
    regs = []
    try:
        conteudo_str = conteudo.decode('utf-8', errors='ignore').lstrip()
        
        # 1. NFSe (Municipal)
        if "<nfse" in conteudo_str.lower() or "<compnfse" in conteudo_str.lower():
            root = ET.fromstring(conteudo_str)
            ns_nfse = "{http://www.abrasf.org.br/nfse.xsd}"
            try:
                n_nota = root.find(f".//{ns_nfse}Numero").text
                v_serv = Decimal(root.find(f".//{ns_nfse}ValorServicos").text)
                emit_cnpj = limpar_cnpj(root.find(f".//{ns_nfse}Cnpj").text)
                regs.append({
                    "Emitente": emit_cnpj, "Nota": int(n_nota), "Série": "SRV", "Espécie": "NFSe", 
                    "CFOP": "SERV", "ST": False, "Anexo": "ANEXO III", "Base_DAS": v_serv, 
                    "Categoria": "RECEITA BRUTA", "Chave": n_nota, "Is_Loc": False
                })
            except: pass
            return regs

        # 2. NFe / NFCe (Estadual)
        root = ET.fromstring(conteudo_str)
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        ide = inf.find(f"{ns}ide")
        n_nota, serie, mod_xml, tp_nf = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text, ide.find(f"{ns}tpNF").text
        especie = "36" if mod_xml == "55" else "42" if mod_xml == "65" else mod_xml

        # Análise de Itens para classificar a nota
        det_um = inf.find(f"{ns}det")
        cfop = det_um.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
        icms_node = det_um.find(f"{ns}imposto/{ns}ICMS")
        possui_st = False
        if icms_node is not None:
            csosn = icms_node.find(f".//{ns}CSOSN")
            if csosn is not None and csosn.text in ["201", "202", "203", "500"]: possui_st = True

        # Valor Total Único do XML para evitar duplicação de produtos
        v_total = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        
        categoria = "RECEITA BRUTA" if emit_cnpj == cnpj_alvo and tp_nf == "1" else "OUTROS"
        anexo = "ANEXO III" if cfop in CFOPS_SERVICO else "ANEXO I"

        regs.append({
            "Emitente": emit_cnpj, "Nota": n_nota, "Série": serie, "Espécie": especie, 
            "CFOP": cfop, "ST": possui_st, "Anexo": anexo, "Base_DAS": v_total, 
            "Categoria": categoria, "Chave": chave, "Is_Loc": False
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

# ─── MOTOR DE CÁLCULO PGDAS (FÓRMULA DE PARTILHA INTEGRAL) ──────────────────

def calcular_aliq_efetiva_detalhada(anexo, possui_st, rb12, st_i, is_loc_manual):
    tab, partilha_map = (TABELA_ANEXO_I, PARTILHA_ANEXO_I) if anexo == "ANEXO I" else (TABELA_ANEXO_III, PARTILHA_ANEXO_III)
    faixa = tab[0]; f_idx = 1
    for f in tab:
        if rb12 <= f[2]: faixa = f; f_idx = f[0]; break
        faixa = f; f_idx = f[0]
    
    ae_bruta = ((rb12 * Decimal(str(faixa[3]))) - Decimal(str(faixa[4]))) / rb12
    p = partilha_map[f_idx]
    red = Decimal("0")
    
    # Se for ST no Anexo I, remove o ICMS
    if anexo == "ANEXO I" and st_i and possui_st:
        red = p.get('icms', 0)
    # Se for Locação Manual no Anexo III, remove o ISS
    elif anexo == "ANEXO III" and is_loc_manual:
        red = p.get('iss', 0)
        
    return ae_bruta * (Decimal("1") - red)

# ─── INTERFACE STREAMLIT (RESTAURO INTEGRAL RIHANNA MODE) ────────────────────

def main():
    st.set_page_config(page_title="Sentinela Group - Auditoria", layout="wide")
    st.markdown("""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
            html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
            .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
            h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
            .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
            .stButton>button { background-color: #d81b60; color: white; border-radius: 20px; font-weight: 600; width: 100%; }
            .stTable { background-color: rgba(255, 255, 255, 0.4); border-radius: 10px; }
        </style>
    """, unsafe_allow_html=True)

    st.title("🛡️ Sentinela Ecosystem - Auditoria Fiel")
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Perfil da Empresa")
        cnpj_input = st.text_input("CNPJ Auditado", key=f"c_{st.session_state.reset_key}")
        cnpj_alvo = limpar_cnpj(cnpj_input)
        rbt12_raw = st.text_input("RBT12 Total do Grupo", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        st.header("⚙️ Parametrização")
        if cnpj_alvo in DIRETRIZES_EMPRESAS:
            config = DIRETRIZES_EMPRESAS[cnpj_alvo]
            st.success(f"Diretriz Ativa: {config['nome']}")
            st_i = st.checkbox("Anexo I: Possui ST?", value=config['anexo_i_st'])
            regra_iii = st.selectbox("Regra Anexo III", ["CHEIA", "LOCACAO"], index=0 if config['anexo_iii_regra']=="CHEIA" else 1)
        else:
            st_i = st.checkbox("Anexo I: Possui ST?", value=True)
            regra_iii = st.selectbox("Regra Anexo III", ["CHEIA", "LOCACAO"], index=0)

        st.subheader("💰 Locação Manual")
        val_loc_raw = st.text_input("Valor de Locação (ISS 0)", value="0,00", key=f"loc_{st.session_state.reset_key}")
        v_loc_manual = Decimal(val_loc_raw.replace(".", "").replace(",", "."))
        
        if st.button("🗑️ Resetar Tudo"): st.session_state.reset_key += 1; st.rerun()

    c1, c2 = st.columns(2)
    with c1: f_norm = st.file_uploader("Movimentação ZIP/XML", accept_multiple_files=True)
    with c2: f_canc = st.file_uploader("Canceladas ZIP/XML", accept_multiple_files=True)

    if st.button("🚀 Iniciar Processamento") and f_norm:
        if not cnpj_alvo or rbt12 == 0: st.error("CNPJ e RBT12 são obrigatórios."); return
        
        canc = set()
        for f in f_canc:
            res_c = processar_recursivo(f.read(), extrair_canceladas)
            for item in res_c:
                if isinstance(item, set): canc.update(item)
                else: canc.add(item)
        
        regs_raw = []
        for f in f_norm: regs_raw.extend(processar_recursivo(f.read(), extrair_dados_detalhados, cnpj_alvo=cnpj_alvo))
        
        if regs_raw:
            df = pd.DataFrame(regs_raw).drop_duplicates(subset=['Chave'])
            df['Cancelada'] = df['Chave'].isin(canc)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), 'Base_DAS'] = Decimal("0")

            # ─── 📊 RESUMO DE CONTINUIDADE (RESTAURADO PARA 55 E 65) ───
            st.subheader("📊 Resumo de Continuidade (Emissão Própria)")
            df_propria = df[(df['Emitente'] == cnpj_alvo) & (~df['Cancelada']) & (df['Espécie'].isin(["36", "42"]))].copy()
            if not df_propria.empty:
                res_cont = df_propria.groupby(['Espécie', 'Série']).agg(
                    Primeira_Nota=('Nota', 'min'), Ultima_Nota=('Nota', 'max'), Qtd_Lida=('Nota', 'nunique')
                ).reset_index()
                res_cont['Modelo'] = res_cont['Espécie'].apply(lambda x: "55 (NFe)" if x=="36" else "65 (NFCe)")
                st.table(res_cont[['Modelo', 'Série', 'Primeira_Nota', 'Ultima_Nota', 'Qtd_Lida']])

            df_f = df[(df["Categoria"] == "RECEITA BRUTA") & (~df['Cancelada']) & (df['Base_DAS'] != 0)].copy()
            
            if v_loc_manual > 0:
                is_loc = True if regra_iii == "LOCACAO" else False
                loc_row = pd.DataFrame([{
                    "Emitente": cnpj_alvo, "Nota": 0, "Espécie": "LOCAÇÃO", "Série": "MANUAL",
                    "CFOP": "LOC", "ST": False, "Anexo": "ANEXO III", "Base_DAS": v_loc_manual,
                    "Categoria": "RECEITA BRUTA", "Cancelada": False, "Chave": "M_LOC", "Is_Loc": is_loc
                }])
                df_f = pd.concat([df_f, loc_row], ignore_index=True)

            if not df_f.empty:
                def calc_row(row):
                    # Se for a linha manual de locação, forçamos a flag de redução
                    flag_loc = row.get('Is_Loc', False)
                    af = calcular_aliq_efetiva_detalhada(row['Anexo'], row['ST'], rbt12, st_i, flag_loc)
                    das = (row['Base_DAS'] * af).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    return af, das

                res_f = df_f.apply(calc_row, axis=1, result_type='expand')
                df_f['Aliq_Final'], df_f['DAS_Valor'] = res_f[0], res_f[1]

                st.subheader("📑 Memorial Analítico por Espécie")
                for esp in sorted(df_f['Espécie'].unique()):
                    with st.expander(f"📌 Espécie {esp}", expanded=True):
                        df_esp = df_f[df_f['Espécie'] == esp].copy()
                        resumo = df_esp.groupby(['Anexo', 'CFOP', 'ST']).agg({'Base_DAS': 'sum', 'DAS_Valor': 'sum'}).reset_index()
                        resumo['Aliq (%)'] = resumo.apply(lambda r: calcular_aliq_efetiva_detalhada(r['Anexo'], r['ST'], rbt12, st_i, (regra_iii=="LOCACAO" if r['Anexo']=="ANEXO III" else False)), axis=1).apply(fmt_aliq)
                        resumo['Base PGDAS'] = resumo['Base_DAS'].apply(fmt_br); resumo['Imposto DAS'] = resumo['DAS_Valor'].apply(fmt_br)
                        st.table(resumo[['Anexo', 'CFOP', 'ST', 'Aliq (%)', 'Base PGDAS', 'Imposto DAS']])

                m1, m2 = st.columns(2)
                m1.metric("Bruto Auditado", f"R$ {fmt_br(df_f['Base_DAS'].sum())}")
                m2.metric("Total DAS a Recolher", f"R$ {fmt_br(df_f['DAS_Valor'].sum())}")

                st.subheader("📋 Auditoria Detalhada (Uma Linha por Nota)")
                df_detalhe = df_f.copy(); df_detalhe['Base_DAS'] = df_detalhe['Base_DAS'].apply(fmt_br)
                st.dataframe(df_detalhe[['Nota', 'Série', 'Espécie', 'CFOP', 'ST', 'Anexo', 'Base_DAS']], use_container_width=True)
        else: st.error("Nenhuma nota processada.")

if __name__ == "__main__": main()
