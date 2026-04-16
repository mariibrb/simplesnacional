"""
Sentinela Ecosystem - Auditoria de Precisão Máxima (VERSÃO NFSe + LOCAÇÃO)
Foco: Bater 7,28% (NFSe/Serviço) e 4,95% (Locação Manual) no Anexo III
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas para bater com as 13 casas do PGDAS
getcontext().prec = 60 

# ─── TABELAS DE PARTILHA (REGRAS OFICIAIS PGDAS) ───────────────────────────
PARTILHA_ANEXO_I = {
    1: {'icms': Decimal("0.34")}, 2: {'icms': Decimal("0.34")},
    3: {'icms': Decimal("0.335")}, 4: {'icms': Decimal("0.335")},
    5: {'icms': Decimal("0.335")}, 6: {'icms': Decimal("0.00")}
}

# Partilha Anexo III: O ISS é o que diferencia o Serviço da Locação
PARTILHA_ANEXO_III = {
    1: {'iss': Decimal("0.32")}, 2: {'iss': Decimal("0.32")},
    3: {'iss': Decimal("0.325")}, 4: {'iss': Decimal("0.325")},
    5: {'iss': Decimal("0.335")}, 6: {'iss': Decimal("0.00")}
}

TABELA_ANEXO_I = [(1, 0, 180000, 0.04, 0), (2, 180000.01, 360000, 0.073, 5940), (3, 360000.01, 720000, 0.095, 13860), (4, 720000.01, 1800000, 0.107, 22500), (5, 1800000.01, 3600000, 0.143, 87300), (6, 3600000.01, 4800000, 0.19, 378000)]
TABELA_ANEXO_III = [(1, 0, 180000, 0.06, 0), (2, 180000.01, 360000, 0.112, 9360), (3, 360000.01, 720000, 0.135, 17640), (4, 720000.01, 1800000, 0.16, 35640), (5, 1800000.01, 3600000, 0.21, 125640), (6, 3600000.01, 4800000, 0.33, 648000)]

CFOPS_SERVICO = {"5933", "6933", "5124", "6124"}
CFOPS_VENDA = {"5101", "5102", "5103", "5105", "5106", "5107", "5108", "5401", "5403", "5405", "6101", "6102", "6401", "6403", "6404"}

# ─── FUNÇÕES DE SUPORTE ──────────────────────────────────────────────────────

def fmt_br(v): return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
def fmt_aliq(v): return f"{(v * 100):,.4f}".replace(".", ",") + "%"
def limpar_cnpj(c): return re.sub(r'\D', '', str(c))

# ─── PROCESSAMENTO XML (VARRRE TODOS OS ITENS - det) ─────────────────────────

def extrair_dados_detalhados(conteudo, cnpj_alvo, radical_grupo):
    regs = []
    try:
        conteudo_str = conteudo.decode('utf-8', errors='ignore').lstrip()
        # Detecção de NFSe (Municipal) vs NFe/NFCe (Estadual)
        is_nfse = "<nfse" in conteudo_str.lower() or "<compnfse" in conteudo_str.lower()
        
        root = ET.fromstring(conteudo_str)
        
        if is_nfse:
            # Lógica Simplificada para NFSe (Mapeia como Serviço)
            # Obs: Ajustar caminhos de tags conforme o padrão da sua prefeitura se necessário
            try:
                ns_nfse = "{http://www.abrasf.org.br/nfse.xsd}" # Exemplo padrão ABRASF
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

        # Lógica NFe / NFCe
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        ide = inf.find(f"{ns}ide")
        n_nota, serie, mod_xml, tp_nf = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text, ide.find(f"{ns}tpNF").text
        especie = "36" if mod_xml == "55" else "42" if mod_xml == "65" else mod_xml

        for det in inf.findall(f"{ns}det"):
            prod, impo = det.find(f"{ns}prod"), det.find(f"{ns}imposto")
            cfop = prod.find(f"{ns}CFOP").text.replace(".", "")
            
            icms_node = impo.find(f".//{ns}ICMS")
            possui_st = False
            if icms_node is not None:
                csosn_tag = icms_node.find(f".//{ns}CSOSN")
                if csosn_tag is not None and csosn_tag.text in ["201", "202", "203", "500"]:
                    possui_st = True

            v_p = Decimal(prod.find(f"{ns}vProd").text)
            v_d = Decimal(prod.find(f"{ns}vDesc").text) if prod.find(f"{ns}vDesc") is not None else Decimal("0")
            v_o = Decimal(prod.find(f"{ns}vOutro").text) if prod.find(f"{ns}vOutro") is not None else Decimal("0")
            v_f = Decimal(prod.find(f"{ns}vFrete").text) if prod.find(f"{ns}vFrete") is not None else Decimal("0")
            base_item = (v_p - v_d + v_o + v_f).quantize(Decimal("0.01"), ROUND_HALF_UP)
            
            categoria = "OUTROS"
            if emit_cnpj == cnpj_alvo and tp_nf == "1":
                if cfop in CFOPS_VENDA or cfop in CFOPS_SERVICO: categoria = "RECEITA BRUTA"
            
            anexo = "ANEXO III" if cfop in CFOPS_SERVICO else "ANEXO I"

            regs.append({
                "Emitente": emit_cnpj, "Nota": n_nota, "Série": serie, "Espécie": especie, 
                "CFOP": cfop, "ST": possui_st, "Anexo": anexo, "Base_DAS": base_item, 
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

# ─── MOTOR DE CÁLCULO PGDAS (HÍBRIDO SERVIÇO vs LOCAÇÃO) ────────────────────

def calcular_aliq_pgdas(anexo, possui_st, rb12, st_i, is_loc_manual):
    tab, partilha = (TABELA_ANEXO_I, PARTILHA_ANEXO_I) if anexo == "ANEXO I" else (TABELA_ANEXO_III, PARTILHA_ANEXO_III)
    faixa = tab[0]; f_idx = 1
    for f in tab:
        if rb12 <= f[2]: faixa = f; f_idx = f[0]; break
        faixa = f; f_idx = f[0]
    
    ae_bruta = ((rb12 * Decimal(str(faixa[3]))) - Decimal(str(faixa[4]))) / rb12
    p = partilha[f_idx]
    
    red = Decimal("0")
    if anexo == "ANEXO I" and st_i and possui_st: 
        red = p.get('icms', 0)
    elif anexo == "ANEXO III" and is_loc_manual: 
        # Reduz o ISS apenas para a linha de Locação Manual
        red = p.get('iss', 0)
        
    return ae_bruta * (Decimal("1") - red)

# ─── INTERFACE STREAMLIT (ROSA RIHANNA MODE) ─────────────────────────────────

def main():
    st.set_page_config(page_title="Sentinela Auditoria", layout="wide")
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
        st.header("👤 Perfil Empresa")
        cnpj_input = st.text_input("CNPJ Auditado", key=f"c_{st.session_state.reset_key}")
        cnpj_alvo = limpar_cnpj(cnpj_input); rad = cnpj_alvo[:8] if cnpj_alvo else ""
        rbt12_raw = st.text_input("RBT12 Total", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        st.header("🧱 Regras PGDAS")
        st_i = st.checkbox("Anexo I: Possui ST (ICMS 0)?", value=True)
        
        st.subheader("💰 Locação Manual")
        val_loc_raw = st.text_input("Valor de Locação (ISS 0)", value="0,00", key=f"loc_{st.session_state.reset_key}")
        v_loc_manual = Decimal(val_loc_raw.replace(".", "").replace(",", "."))
        
        if st.button("🗑️ Resetar Tudo"): st.session_state.reset_key += 1; st.rerun()

    c1, c2 = st.columns(2)
    with c1: f_norm = st.file_uploader("Movimentação ZIP/XML (NFe/NFCe/NFSe)", accept_multiple_files=True)
    with c2: f_canc = st.file_uploader("Canceladas ZIP/XML", accept_multiple_files=True)

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_alvo or rbt12 == 0: st.error("Dados incompletos."); return
        
        canc = set()
        for f in f_canc:
            res_c = processar_recursivo(f.read(), extrair_canceladas)
            for item in res_c:
                if isinstance(item, set): canc.update(item)
                else: canc.add(item)
        
        regs_raw = []
        for f in f_norm: regs_raw.extend(processar_recursivo(f.read(), extrair_dados_detalhados, cnpj_alvo=cnpj_alvo, radical_grupo=rad))
        
        if regs_raw:
            df = pd.DataFrame(regs_raw)
            df['Cancelada'] = df['Chave'].isin(canc)
            
            # 📊 CONTINUIDADE (Apenas Emissão Própria real)
            st.subheader("📊 Resumo de Continuidade (NF-e / NFC-e)")
            df_cont = df[(df['Emitente'] == cnpj_alvo) & (~df['Cancelada']) & (df['Espécie'] != "NFSe")].copy()
            if not df_cont.empty:
                res_cont = df_cont.groupby(['Espécie', 'Série']).agg(
                    Primeira_Nota=('Nota', 'min'),
                    Ultima_Nota=('Nota', 'max'),
                    Qtd_Lida=('Nota', 'nunique')
                ).reset_index()
                st.table(res_cont)

            # Filtro para Apuração
            df_f = df[(df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])) & (~df['Cancelada']) & (df['Base_DAS'] != 0)].copy()
            
            # Valor de Locação Manual (Caminho da Redução do ISS)
            if v_loc_manual > 0:
                loc_row = pd.DataFrame([{
                    "Emitente": cnpj_alvo, "Nota": 0, "Espécie": "LOCAÇÃO", "Série": "MANUAL",
                    "CFOP": "LOC", "ST": False, "Anexo": "ANEXO III", "Base_DAS": v_loc_manual,
                    "Categoria": "RECEITA BRUTA", "Cancelada": False, "Chave": "M_LOC", "Is_Loc": True
                }])
                df_f = pd.concat([df_f, loc_row], ignore_index=True)

            if not df_f.empty:
                def calc_row(row):
                    af = calcular_aliq_pgdas(row['Anexo'], row['ST'], rbt12, st_i, row['Is_Loc'])
                    mult = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                    das = ((row['Base_DAS'] * mult) * af).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    return af, das

                res_f = df_f.apply(calc_row, axis=1, result_type='expand')
                df_f['Aliq_Final'], df_f['DAS_Valor'] = res_f[0], res_f[1]

                st.subheader("📑 Memorial Analítico por Espécie")
                for esp in sorted(df_f['Espécie'].unique()):
                    with st.expander(f"📌 {esp}", expanded=True):
                        df_esp = df_f[df_f['Espécie'] == esp].copy()
                        resumo = df_esp.groupby(['Anexo', 'CFOP', 'ST', 'Is_Loc']).agg({'Base_DAS': 'sum', 'DAS_Valor': 'sum'}).reset_index()
                        resumo['Aliq (%)'] = resumo.apply(lambda r: calcular_aliq_pgdas(r['Anexo'], r['ST'], rbt12, st_i, r['Is_Loc']), axis=1).apply(fmt_aliq)
                        resumo['Base PGDAS'] = resumo['Base_DAS'].apply(fmt_br); resumo['Imposto DAS'] = resumo['DAS_Valor'].apply(fmt_br)
                        st.table(resumo[['Anexo', 'CFOP', 'ST', 'Aliq (%)', 'Base PGDAS', 'Imposto DAS']])

                st.subheader("🧱 Consolidação por Anexo")
                res_an = df_f.groupby('Anexo').agg({'Base_DAS': 'sum', 'DAS_Valor': 'sum'}).reset_index()
                res_an['Base Líquida'] = res_an['Base_DAS'].apply(fmt_br); res_an['Total DAS'] = res_an['DAS_Valor'].apply(fmt_br)
                st.table(res_an[['Anexo', 'Base Líquida', 'Total DAS']])

                m1, m2, m3 = st.columns(3)
                m1.metric("Bruto Auditado", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_DAS'].sum())}")
                m2.metric("Total DAS", f"R$ {fmt_br(df_f['DAS_Valor'].sum())}")
                m3.metric("Alíq. Média", fmt_aliq(df_f['DAS_Valor'].sum() / df_f['Base_DAS'].sum()) if df_f['Base_DAS'].sum() > 0 else "0%")

                st.subheader("📋 Auditoria Detalhada (Uma Linha por Nota)")
                df_detalhe = df_f.groupby(['Nota', 'Série', 'Espécie', 'CFOP', 'ST', 'Anexo', 'Is_Loc']).agg({'Base_DAS': 'sum'}).reset_index()
                df_detalhe['Base_DAS'] = df_detalhe['Base_DAS'].apply(fmt_br)
                st.dataframe(df_detalhe, use_container_width=True)
        else: st.error("Nenhuma nota processada.")

if __name__ == "__main__": main()
