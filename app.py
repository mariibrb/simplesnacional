"""
Sentinela Group - Auditoria Consolidada (VERSÃO INTEGRAL - TOTAIS POR ANEXO)
Foco: PGDAS Matriz/Filiais, Alíquota sobre RBT12, Resumo por Anexo e Detalhamento
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão interna de 60 casas para cálculos fiscais de alta fidelidade
getcontext().prec = 60 

# ─── REGRAS FISCAIS UNIVERSAIS (TABELAS OFICIAIS) ───────────────────────────
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.34")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.34")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.335")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.335")),
    (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00"), Decimal("0.335")),
    (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.19"), Decimal("378000.00"), Decimal("0.335")),
]

TABELA_ANEXO_II = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.045"), Decimal("0.00"), Decimal("0.32")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.078"), Decimal("5940.00"), Decimal("0.32")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.10"), Decimal("13860.00"), Decimal("0.32")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.112"), Decimal("22500.00"), Decimal("0.32")),
    (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.147"), Decimal("85500.00"), Decimal("0.32")),
    (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.30"), Decimal("720000.00"), Decimal("0.32")),
]

CFOPS_VENDA = {
    "5101", "5102", "5103", "5105", "5106", "5107", "5108",
    "6101", "6102", "6103", "6105", "6106", "6107", "6108",
    "5401", "5403", "5405", "6401", "6403", "6404"
}
CFOPS_DEVOL_VEN_PROPRIA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_DEVOL_VEN_TERCEIRO = {"5201", "5202", "5411", "6201", "6202", "6411"}
CFOPS_EXCLUSAO_SOMA = {"5949", "6905", "6209", "6152", "5151", "5152", "6151", "1949", "2949"}
CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

# ─── FUNÇÕES DE FORMATAÇÃO PT-BR ─────────────────────────────────────────────

def fmt_br(valor):
    try:
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except: return "0,00"

def fmt_aliq(valor):
    try:
        val_perc = (valor * Decimal("100")).quantize(Decimal("0.0000000000001"), ROUND_HALF_UP)
        return f"{val_perc:,.13f}".replace(".", ",") + "%"
    except: return "0,0000000000000%"

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
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
        .stExpander { background-color: rgba(255, 255, 255, 0.2); border-radius: 10px; border: none; }
    </style>
""", unsafe_allow_html=True)

# ─── FUNÇÕES DE APOIO XML ───────────────────────────────────────────────────

def extrair_chaves_cancelamento(conteudo):
    chaves = set()
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        for ev in root.findall(f".//{ns}infEvento"):
            if ev.find(f"{ns}tpEvento").text == "110111":
                chaves.add(ev.find(f"{ns}chNFe").text)
        inf = root.find(f".//{ns}infNFe")
        if inf is not None: chaves.add(inf.attrib.get('Id', '')[3:])
    except: pass
    return chaves

def extrair_dados_xml(conteudo, chaves_vistas, radical_cnpj):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        is_o_emissor_grupo = emit_cnpj.startswith(radical_cnpj)
        is_o_destinatario_grupo = dest_cnpj.startswith(radical_cnpj)

        if not (is_o_emissor_grupo or is_o_destinatario_grupo): return []
            
        ide = inf.find(f"{ns}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text
        tp_nf = ide.find(f"{ns}tpNF").text 

        for det in inf.findall(f"{ns}det"):
            prod, impo = det.find(f"{ns}prod"), det.find(f"{ns}imposto")
            v_p = Decimal(prod.find(f"{ns}vProd").text)
            v_desc = Decimal(prod.find(f"{ns}vDesc").text) if prod.find(f"{ns}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns}vOutro").text) if prod.find(f"{ns}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns}vFrete").text) if prod.find(f"{ns}vFrete") is not None else Decimal("0")
            
            v_st = Decimal("0")
            icms = impo.find(f".//{ns}ICMS")
            if icms is not None:
                vst = icms.find(f".//{ns}vICMSST")
                if vst is not None: v_st = Decimal(vst.text)

            base_das = (v_p - v_desc + v_outro + v_frete).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns}CFOP").text.replace(".", "")
            
            categoria = "OUTROS"
            if is_o_emissor_grupo: 
                if tp_nf == "1": # Saída Grupo
                    if cfop in CFOPS_VENDA and cfop not in CFOPS_EXCLUSAO_SOMA:
                        categoria = "RECEITA BRUTA"
                else: # Entrada Própria
                    if cfop in CFOPS_DEVOL_VEN_PROPRIA:
                        categoria = "DEVOLUÇÃO VENDA"
            else: # Terceiro devolvendo
                if tp_nf == "1" and is_o_destinatario_grupo:
                    if cfop in CFOPS_DEVOL_VEN_TERCEIRO:
                        categoria = "DEVOLUÇÃO VENDA"

            regs.append({
                "Unidade_CNPJ": emit_cnpj if is_o_emissor_grupo else dest_cnpj,
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, 
                "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "Base_DAS": base_das, "Tipo": "SAÍDA" if tp_nf == "1" else "ENTRADA",
                "Categoria": categoria, "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo_generic(arquivo_bytes, func_target, **kwargs):
    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                content = z.read(nome)
                if nome.lower().endswith('.xml'):
                    res = func_target(content, **kwargs)
                    if isinstance(res, set): results.extend(list(res))
                    else: results.extend(res)
                elif nome.lower().endswith('.zip'):
                    results.extend(processar_recursivo_generic(content, func_target, **kwargs))
    except:
        res = func_target(arquivo_bytes, **kwargs)
        if isinstance(res, set): results.extend(list(res))
        else: results.extend(res)
    return results

# ─── MOTOR DE CÁLCULO E INTERFACE ────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela Ecosystem - Auditoria Consolidada")
    
    if 'reset_key' not in st.session_state:
        st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Grupo Econômico")
        cnpj_input = st.text_input("CNPJ (Matriz ou Filial)", key=f"cnpj_in_{st.session_state.reset_key}")
        radical = limpar_cnpj(cnpj_input)[:8] if cnpj_input else ""
        
        st.header("⚙️ Parâmetros Consolidados")
        rbt12_raw = st.text_input("RBT12 Total do Grupo", value="", key=f"rbt12_in_{st.session_state.reset_key}")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    c1, c2 = st.columns(2)
    with c1: 
        f_norm = st.file_uploader("Movimentação Grupo", accept_multiple_files=True, type=["xml", "zip"], key=f"u1_{st.session_state.reset_key}")
    with c2: 
        f_canc = st.file_uploader("Canceladas Grupo", accept_multiple_files=True, type=["xml", "zip"], key=f"u2_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria Grupo") and f_norm:
        if not radical or rbt12 == 0:
            st.error("Informe o CNPJ e o RBT12 Acumulado."); return

        ch_canc = set()
        for f in f_canc: ch_canc.update(processar_recursivo_generic(f.read(), extrair_chaves_cancelamento))

        ch_vistas, regs = set(), []
        for f in f_norm: regs.extend(processar_recursivo_generic(f.read(), extrair_dados_xml, chaves_vistas=ch_vistas, radical_cnpj=radical))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(ch_canc)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), ['Base_DAS']] = Decimal("0")

            def obter_aliq_efetiva(anexo, st_val, rb_total):
                tab = TABELA_ANEXO_I if anexo == "ANEXO I" else TABELA_ANEXO_II
                faixa = tab[0]
                for f in tab:
                    if rb_total <= f[2]: faixa = f; break
                    faixa = f
                _, _, _, aliq_nom, deducao, p_icms_ipi = faixa
                ae = ((rb_total * aliq_nom) - deducao) / rb_total if rb_total > 0 else aliq_nom
                return ae * (Decimal("1.0") - p_icms_ipi) if st_val else ae

            aliqs_grupo = {
                "ANEXO I_False": obter_aliq_efetiva("ANEXO I", False, rbt12),
                "ANEXO I_True": obter_aliq_efetiva("ANEXO I", True, rbt12),
                "ANEXO II_False": obter_aliq_efetiva("ANEXO II", False, rbt12),
                "ANEXO II_True": obter_aliq_efetiva("ANEXO II", True, rbt12),
            }

            df_f = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            if not df_f.empty:
                def calcular_das(row):
                    key = f"{row['Anexo']}_{row['ST']}"
                    af = aliqs_grupo[key]
                    mult = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                    base = (row['Base_DAS'] * mult).quantize(Decimal("0.01"), ROUND_HALF_UP)
                    return af, base, (base * af).quantize(Decimal("0.01"), ROUND_HALF_UP)

                res_fisc = df_f.apply(calcular_das, axis=1, result_type='expand')
                df_f['Aliq_F'], df_f['Base_F'], df_f['DAS'] = res_fisc[0], res_fisc[1], res_fisc[2]

                st.subheader("📑 Memorial Analítico Unificado")
                resumo = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'Base_F': 'sum', 'DAS': 'sum'}).reset_index()
                resumo['Aliq_Ef'] = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria'])['Aliq_F'].first().values
                
                res_display = resumo.copy()
                res_display['Aliq (%)'] = res_display['Aliq_Ef'].apply(fmt_aliq)
                res_display['Base PGDAS'] = res_display['Base_F'].apply(fmt_br)
                res_display['Imposto DAS'] = res_display['DAS'].apply(fmt_br)
                st.table(res_display[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq (%)', 'Base PGDAS', 'Imposto DAS']])

                # ─── NOVO: TOTAIS CONSOLIDADOS POR ANEXO ───
                st.subheader("🧱 Resumo Consolidado por Anexo")
                resumo_anexo = df_f.groupby(['Anexo']).agg({'Base_F': 'sum', 'DAS': 'sum'}).reset_index()
                resumo_anexo['Base Líquida'] = resumo_anexo['Base_F'].apply(fmt_br)
                resumo_anexo['DAS Total'] = resumo_anexo['DAS'].apply(fmt_br)
                st.table(resumo_anexo[['Anexo', 'Base Líquida', 'DAS Total']])

                st.subheader("🔍 Detalhamento de Notas")
                for name, group in df_f.groupby(['Anexo', 'Categoria']):
                    with st.expander(f"Ver notas do {name[0]} - {name[1]}"):
                        notas_anexo = group[group['Base_DAS'] != 0].copy()
                        notas_anexo['Valor'] = notas_anexo['Base_DAS'].apply(fmt_br)
                        st.dataframe(notas_anexo[['Unidade_CNPJ', 'Nota', 'Série', 'CFOP', 'ST', 'Valor', 'Tipo']], use_container_width=True)

                st.markdown("---")
                m1, m2, m3 = st.columns(3)
                m1.metric("Bruto Grupo", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_F'].sum())}")
                m2.metric("(-) Devoluções Grupo", f"R$ {fmt_br(abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_F'].sum()))}")
                m3.metric("DAS Total a Recolher", f"R$ {fmt_br(df_f['DAS'].sum())}")
            
            st.subheader("📋 Auditoria Detalhada (Todas as notas)")
            st.dataframe(df[['Unidade_CNPJ', 'Nota', 'CFOP', 'Categoria', 'Base_DAS', 'Cancelada']], use_container_width=True)
        else: st.error("Nenhuma nota encontrada.")

if __name__ == "__main__": main()
