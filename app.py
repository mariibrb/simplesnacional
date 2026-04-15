"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL)
Foco: PGDAS Anexos I e II, Redução de ST, Gestão de Cancelamentos via Upload e Matrioscas
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 60 casas para cálculos fiscais de alta fidelidade
getcontext().prec = 60 

# ─── REGRAS FISCAIS UNIVERSAIS ──────────────────────────────────────────────
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3350")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]

TABELA_ANEXO_II = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.045"), Decimal("0.00"), Decimal("0.3200")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.078"), Decimal("5940.00"), Decimal("0.3200")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.10"), Decimal("13860.00"), Decimal("0.3200")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.112"), Decimal("22500.00"), Decimal("0.3200")),
]

CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_DEVOLUCAO_VENDA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

# ─── ESTILIZAÇÃO ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
    </style>
""", unsafe_allow_html=True)

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_chaves_cancelamento(conteudo):
    chaves = set()
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns_nfe = "{http://www.portalfiscal.inf.br/nfe}"
        # Busca em Eventos de Cancelamento
        for inf_evento in root.findall(f".//{ns_nfe}infEvento"):
            tp_ev = inf_evento.find(f"{ns_nfe}tpEvento").text
            if tp_ev == "110111":
                chaves.add(inf_evento.find(f"{ns_nfe}chNFe").text)
        # Busca em Notas Fiscais (se subirem o XML da nota como cancelada)
        inf_nfe = root.find(f".//{ns_nfe}infNFe")
        if inf_nfe is not None:
            chaves.add(inf_nfe.attrib.get('Id', '')[3:])
    except: pass
    return chaves

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns_nfe = "{http://www.portalfiscal.inf.br/nfe}"
        
        inf = root.find(f".//{ns_nfe}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns_nfe}emit/{ns_nfe}CNPJ").text)
        dest_node = inf.find(f"{ns_nfe}dest/{ns_nfe}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        emissao_propria = (emit_cnpj == cnpj_cliente)
        if cnpj_cliente and not (emit_cnpj == cnpj_cliente or dest_cnpj == cnpj_cliente):
            return []
            
        ide = inf.find(f"{ns_nfe}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns_nfe}nNF").text), ide.find(f"{ns_nfe}serie").text, ide.find(f"{ns_nfe}mod").text
        tp_nf = ide.find(f"{ns_nfe}tpNF").text 

        for det in inf.findall(f"{ns_nfe}det"):
            prod = det.find(f"{ns_nfe}prod")
            imposto = det.find(f"{ns_nfe}imposto")
            
            v_p = Decimal(prod.find(f"{ns_nfe}vProd").text)
            v_desc = Decimal(prod.find(f"{ns_nfe}vDesc").text) if prod.find(f"{ns_nfe}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns_nfe}vOutro").text) if prod.find(f"{ns_nfe}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns_nfe}vFrete").text) if prod.find(f"{ns_nfe}vFrete") is not None else Decimal("0")
            
            # Captura ICMS ST para abatimento da Base Contábil
            v_st = Decimal("0")
            icms_node = imposto.find(f".//{ns_nfe}ICMS")
            if icms_node is not None:
                st_node = icms_node.find(f".//{ns_nfe}vICMSST")
                if st_node is not None: v_st = Decimal(st_node.text)
            
            base_item = (v_p - v_desc + v_outro + v_frete - v_st).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns_nfe}CFOP").text.replace(".", "")
            
            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, "Origem": "PRÓPRIA" if emissao_propria else "TERCEIROS",
                "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "Valor_Contabil": v_p + v_outro + v_frete,
                "Valor_ST": v_st,
                "Base_DAS_Item": base_item,
                "Tipo": "SAÍDA" if tp_nf == "1" else "ENTRADA",
                "Categoria": "RECEITA BRUTA" if emissao_propria and tp_nf == "1" else ("DEVOLUÇÃO VENDA" if not emissao_propria and cfop in CFOPS_DEVOLUCAO_VENDA else "OUTROS"),
                "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo_cancelamento(arquivo_bytes):
    chaves = set()
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                content = z.read(nome)
                if nome.lower().endswith('.xml'): chaves.update(extrair_chaves_cancelamento(content))
                elif nome.lower().endswith('.zip'): chaves.update(processar_recursivo_cancelamento(content))
    except: chaves.update(extrair_chaves_cancelamento(arquivo_bytes))
    return chaves

def processar_recursivo_notas(arquivo_bytes, chaves_vistas, cnpj_cli):
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                content = z.read(nome)
                if nome.lower().endswith('.xml'): registros.extend(extrair_dados_xml(content, chaves_vistas, cnpj_cli))
                elif nome.lower().endswith('.zip'): registros.extend(processar_recursivo_notas(content, chaves_vistas, cnpj_cli))
    except: registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, cnpj_cli))
    return registros

# ─── INTERFACE E MOTOR PRINCIPAL ─────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria e Memorial")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente Auditado")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Total", value="", key=f"r_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    c_up1, c_up2 = st.columns(2)
    with c_up1:
        f_norm = st.file_uploader("Upload XMLs Vendas/Entradas", accept_multiple_files=True, type=["xml", "zip"], key=f"f1_{st.session_state.reset_key}")
    with c_up2:
        f_canc = st.file_uploader("Upload XMLs Canceladas", accept_multiple_files=True, type=["xml", "zip"], key=f"f2_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_cli:
            st.error("Informe o CNPJ.")
            return

        # 1. Mapear chaves canceladas
        ch_canceladas = set()
        for f in f_canc: ch_canceladas.update(processar_recursivo_cancelamento(f.read()))

        # 2. Processar notas
        ch_vistas, regs = set(), []
        for f in f_norm: regs.extend(processar_recursivo_notas(f.read(), ch_vistas, cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(ch_canceladas)
            
            # Zera faturamento de canceladas e terceiros (exceto devolução tributável)
            df.loc[df['Cancelada'], ['Valor_Contabil', 'Valor_ST', 'Base_DAS_Item']] = Decimal("0")
            df.loc[df['Origem'] == "TERCEIROS", ['Valor_Contabil', 'Valor_ST', 'Base_DAS_Item']] = Decimal("0")

            # ─── RESUMO DE CONTINUIDADE (TIPO E SÉRIE) ───
            st.subheader("📊 Resumo de Continuidade por Tipo e Série")
            res_series = df.groupby(['Origem', 'Tipo', 'Modelo', 'Série']).agg(
                Nota_Inicial=('Nota', 'min'), Nota_Final=('Nota', 'max'), Qtd_Notas=('Nota', 'nunique')
            ).reset_index()
            st.table(res_series)

            # ─── MEMORIAL FISCAL ───
            df_f = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()

            def obter_aliq(row, rb):
                t = TABELA_ANEXO_I if row['Anexo'] == "ANEXO I" else TABELA_ANEXO_II
                an, de, pi = t[0][3], t[0][4], t[0][5]
                for _, i, f, n, d, p in t:
                    if rb <= f: an, de, pi = n, d, p; break
                ae = ((rb * an) - de) / rb if rb > 0 else an
                return ae * (Decimal("1.0") - pi) if row['ST'] else ae

            resumo = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'Valor_Contabil': 'sum', 'Valor_ST': 'sum', 'Base_DAS_Item': 'sum'}).reset_index()
            resumo['Base_Líquida'] = resumo.apply(lambda x: (x['Base_DAS_Item'] * Decimal("-1") if x['Categoria'] == "DEVOLUÇÃO VENDA" else x['Base_DAS_Item']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
            resumo['Aliq_Final'] = resumo.apply(lambda x: obter_aliq(x, rbt12), axis=1)
            resumo['DAS'] = resumo.apply(lambda row: (row['Base_Líquida'] * row['Aliq_Final']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)
            resumo['Aliq_Perc'] = resumo['Aliq_Final'].apply(lambda x: f"{(x*100):.13f}%")
            
            st.subheader("📑 Resumo Analítico por CFOP (Base = Contábil - ST)")
            st.table(resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq_Perc', 'Valor_Contabil', 'Valor_ST', 'Base_Líquida', 'DAS']])

            st.markdown("---")
            m1, m2, m3 = st.columns(3)
            m1.metric("Faturamento Contábil", f"R$ {resumo['Valor_Contabil'].sum():,.2f}")
            m2.metric("ST Abatido da Base", f"R$ {resumo['Valor_ST'].sum():,.2f}")
            m3.metric("Total DAS", f"R$ {resumo['DAS'].sum():,.2f}")
            
            st.subheader("📋 Auditoria de Cancelamentos e Rastreabilidade")
            st.dataframe(df[['Nota', 'Origem', 'CFOP', 'Base_DAS_Item', 'Cancelada', 'Chave']], use_container_width=True)
        else:
            st.error("Nenhuma nota processada.")

if __name__ == "__main__":
    main()
