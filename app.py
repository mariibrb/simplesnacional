"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL - BLINDAGEM TOTAL)
Foco: PGDAS Anexos I e II, Faixas 1-6, Blindagem de Devolução por Identidade de Destinatário
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

# ─── REGRAS FISCAIS UNIVERSAIS (6 FAIXAS COMPLETAS) ─────────────────────────
TABELA_ANEXO_I = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3350")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
    (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.143"), Decimal("87300.00"), Decimal("0.3350")),
    (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.19"), Decimal("378000.00"), Decimal("0.3350")),
]

TABELA_ANEXO_II = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.045"), Decimal("0.00"), Decimal("0.3200")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.078"), Decimal("5940.00"), Decimal("0.3200")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.10"), Decimal("13860.00"), Decimal("0.3200")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.112"), Decimal("22500.00"), Decimal("0.3200")),
    (5, Decimal("1800000.01"), Decimal("3600000.00"), Decimal("0.147"), Decimal("85500.00"), Decimal("0.3200")),
    (6, Decimal("3600000.01"), Decimal("4800000.00"), Decimal("0.30"), Decimal("720000.00"), Decimal("0.3200")),
]

CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_DEVOLUCAO_VENDA = {"1201", "1202", "1411", "2201", "2202", "2411"}
CFOPS_EXCLUSAO_DAS = {"5949", "6905", "6209", "6152", "6202", "6411", "5201", "5202", "5411", "1203", "1204", "2203", "2204", "5151", "5152", "6151"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; }
        .stButton>button { background-color: #d81b60; color: white; border-radius: 20px; font-weight: 600; width: 100%; }
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
        for inf_evento in root.findall(f".//{ns_nfe}infEvento"):
            tp_ev = inf_evento.find(f"{ns_nfe}tpEvento").text
            if tp_ev == "110111":
                chaves.add(inf_evento.find(f"{ns_nfe}chNFe").text)
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
        
        is_propria = (emit_cnpj == cnpj_cliente)
        is_destinataria = (dest_cnpj == cnpj_cliente)

        # Se o cliente não é nem emitente nem destinatário, ignora a nota.
        if not (is_propria or is_destinataria):
            return []
            
        ide = inf.find(f"{ns_nfe}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns_nfe}nNF").text), ide.find(f"{ns_nfe}serie").text, ide.find(f"{ns_nfe}mod").text
        tp_nf = ide.find(f"{ns_nfe}tpNF").text 

        for det in inf.findall(f"{ns_nfe}det"):
            prod, imposto = det.find(f"{ns_nfe}prod"), det.find(f"{ns_nfe}imposto")
            v_p = Decimal(prod.find(f"{ns_nfe}vProd").text)
            v_desc = Decimal(prod.find(f"{ns_nfe}vDesc").text) if prod.find(f"{ns_nfe}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns_nfe}vOutro").text) if prod.find(f"{ns_nfe}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns_nfe}vFrete").text) if prod.find(f"{ns_nfe}vFrete") is not None else Decimal("0")
            
            v_st, v_ipi = Decimal("0"), Decimal("0")
            icms_node = imposto.find(f".//{ns_nfe}ICMS")
            if icms_node is not None:
                st_node = icms_node.find(f".//{ns_nfe}vICMSST")
                if st_node is not None: v_st = Decimal(st_node.text)
            ipi_node = imposto.find(f".//{ns_nfe}IPI")
            if ipi_node is not None:
                v_ipi_val = ipi_node.find(f".//{ns_nfe}vIPI")
                if v_ipi_val is not None: v_ipi = Decimal(v_ipi_val.text)

            v_contabil = (v_p + v_ipi + v_st + v_outro + v_frete - v_desc).quantize(Decimal("0.01"), ROUND_HALF_UP)
            base_das = (v_p - v_desc + v_outro + v_frete).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns_nfe}CFOP").text.replace(".", "")
            
            # ─── HIERARQUIA FISCAL RIGOROSA ───
            categoria = "OUTROS"
            
            # 1. RECEITA BRUTA: Deve ser emissão PRÓPRIA e SAÍDA (Tipo 1)
            if is_propria and tp_nf == "1":
                if cfop not in CFOPS_EXCLUSAO_DAS:
                    categoria = "RECEITA BRUTA"
            
            # 2. DEVOLUÇÃO VENDA (ABATE DAS): Deve ser ENTRADA (Tipo 0), CFOP de Devolução e VOCÊ ser o DESTINATÁRIO
            elif is_destinataria and tp_nf == "0":
                if cfop in CFOPS_DEVOLUCAO_VENDA:
                    categoria = "DEVOLUÇÃO VENDA"

            regs.append({
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, "Origem": "PRÓPRIA" if is_propria else "TERCEIROS",
                "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "V_Contabil": v_contabil, "V_ST": v_st, "V_IPI": v_ipi,
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
    st.title("🛡️ Sentinela Ecosystem - Auditoria e Memorial")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente Auditado")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Total", value="", key=f"r_{st.session_state.reset_key}")
        rbt12_clean = rbt12_raw.replace(".", "").replace(",", ".")
        rbt12 = Decimal(rbt12_clean) if rbt12_clean else Decimal("0")
        
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    c_up1, c_up2 = st.columns(2)
    with c_up1:
        f_norm = st.file_uploader("Movimentação (Vendas/Entradas)", accept_multiple_files=True, type=["xml", "zip"], key=f"f1_{st.session_state.reset_key}")
    with c_up2:
        f_canc = st.file_uploader("Exclusão (Canceladas)", accept_multiple_files=True, type=["xml", "zip"], key=f"f2_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_cli:
            st.error("Informe o CNPJ."); return

        # 1. Processar Cancelamentos (Recursivo)
        ch_canc = set()
        for f in f_canc:
            ch_canc.update(processar_recursivo_generic(f.read(), extrair_chaves_cancelamento))

        # 2. Processar Notas Normais (Recursivo)
        ch_vistas, regs = set(), []
        for f in f_norm:
            regs.extend(processar_recursivo_generic(f.read(), extrair_dados_xml, chaves_vistas=ch_vistas, cnpj_cliente=cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(ch_canc)
            
            # Regra de Ouro: Zera faturamento inválido (Canceladas, Outros e Terceiros que não são Devolução de Venda)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), ['V_Contabil', 'V_ST', 'V_IPI', 'Base_DAS']] = Decimal("0")

            # Resumo por Série
            st.subheader("📊 Continuidade por Série")
            st.table(df.groupby(['Origem', 'Tipo', 'Modelo', 'Série']).agg(Ini=('Nota', 'min'), Fim=('Nota', 'max'), Qtd=('Nota', 'nunique')).reset_index())

            # Motor Fiscal Faixas 1-6
            def calcular_aliq_efetiva(row, rb_total):
                tab = TABELA_ANEXO_I if row['Anexo'] == "ANEXO I" else TABELA_ANEXO_II
                faixa = tab[0]
                for f in tab:
                    if rb_total <= f[2]: faixa = f; break
                    faixa = f
                _, _, _, a_nom, ded, p_ic = faixa
                ae = ((rb_total * a_nom) - ded) / rb_total if rb_total > 0 else a_nom
                af = ae * (Decimal("1.0") - p_ic) if row['ST'] else ae
                mult = Decimal("-1") if row['Categoria'] == "DEVOLUÇÃO VENDA" else Decimal("1")
                base_calc = (row['Base_DAS'] * mult).quantize(Decimal("0.01"), ROUND_HALF_UP)
                return base_calc, af, (base_calc * af).quantize(Decimal("0.01"), ROUND_HALF_UP)

            df_f = df[df["Categoria"].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])].copy()
            res_fiscal = df_f.apply(lambda r: calcular_aliq_efetiva(r, rbt12), axis=1, result_type='expand')
            df_f['Base_Final'], df_f['Aliq_F'], df_f['DAS'] = res_fiscal[0], res_fiscal[1], res_fiscal[2]

            st.subheader("📑 Memorial Analítico (CFOPS Blindados por Identidade)")
            resumo = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'V_Contabil': 'sum', 'Base_Final': 'sum', 'DAS': 'sum'}).reset_index()
            resumo['Aliq_Ef (%)'] = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria'])['Aliq_F'].first().values
            resumo['Aliq_Ef (%)'] = resumo['Aliq_Ef (%)'].apply(lambda x: f"{(x*100):.10f}%")
            st.table(resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq_Ef (%)', 'V_Contabil', 'Base_Final', 'DAS']])

            st.markdown("---")
            m1, m2, m3 = st.columns(3)
            m1.metric("Bruto Tributável", f"R$ {df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_Final'].sum():,.2f}")
            m2.metric("(-) Devoluções de Venda", f"R$ {abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_Final'].sum()):,.2f}")
            m3.metric("DAS Líquido Final", f"R$ {df_f['DAS'].sum():,.2f}")
            
            st.subheader("📋 Auditoria Detalhada")
            st.dataframe(df[['Nota', 'CFOP', 'V_Contabil', 'Base_DAS', 'Categoria', 'Tipo', 'Origem', 'Cancelada']], use_container_width=True)
        else: st.error("Nenhuma nota encontrada.")

if __name__ == "__main__": main()
