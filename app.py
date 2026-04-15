"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL - PADRÃO BRASIL)
Foco: PGDAS Anexos I e II, Faixas 1-6, Formatação Monetária PT-BR e Precisão Máxima
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd
import locale

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

CFOPS_DEVOLUCAO_VENDA = {"1201", "1202", "1411", "2201", "2202", "2411", "5201", "5202", "5411", "6201", "6202", "6411"}
CFOPS_EXCLUSAO_DAS = {"5949", "6905", "6209", "6152", "5151", "5152", "6151", "6202", "6411", "5202", "5411"}
CFOPS_INDUSTRIA = {"5101", "6101", "5103", "5105", "5401", "6401"}
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404", "1411", "2411", "5411", "6411"}

# ─── FUNÇÕES DE FORMATAÇÃO PT-BR ─────────────────────────────────────────────

def fmt_br(valor):
    """Formata Decimal/Float para string monetária brasileira"""
    try:
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return "0,00"

def fmt_aliq(valor):
    """Formata alíquota com 15 casas e vírgula decimal"""
    try:
        val_perc = valor * 100
        return f"{val_perc:.15f}".replace(".", ",") + "%"
    except:
        return "0,000000000000000%"

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
            if tp_ev == "110111": chaves.add(inf_evento.find(f"{ns_nfe}chNFe").text)
        inf_nfe = root.find(f".//{ns_nfe}infNFe")
        if inf_nfe is not None: chaves.add(inf_nfe.attrib.get('Id', '')[3:])
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
        
        is_o_emissor_alvo = (emit_cnpj == cnpj_cliente)
        is_o_destinatario_alvo = (dest_cnpj == cnpj_cliente)

        if not (is_o_emissor_alvo or is_o_destinatario_alvo): return []
            
        ide = inf.find(f"{ns_nfe}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns_nfe}nNF").text), ide.find(f"{ns_nfe}serie").text, ide.find(f"{ns_nfe}mod").text
        tp_nf = ide.find(f"{ns_nfe}tpNF").text 

        for det in inf.findall(f"{ns_nfe}det"):
            prod, imposto = det.find(f"{ns_nfe}prod"), det.find(f"{ns_nfe}imposto")
            v_p = Decimal(prod.find(f"{ns_nfe}vProd").text)
            v_desc = Decimal(prod.find(f"{ns_nfe}vDesc").text) if prod.find(f"{ns_nfe}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns_nfe}vOutro").text) if prod.find(f"{ns_nfe}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns_nfe}vFrete").text) if prod.find(f"{ns_nfe}vFrete") is not None else Decimal("0")
            
            v_st = Decimal("0")
            icms_node = imposto.find(f".//{ns_nfe}ICMS")
            if icms_node is not None:
                st_node = icms_node.find(f".//{ns_nfe}vICMSST")
                if st_node is not None: v_st = Decimal(st_node.text)
            
            v_contabil = (v_p + v_st + v_outro + v_frete - v_desc).quantize(Decimal("0.01"), ROUND_HALF_UP)
            base_das = (v_p - v_desc + v_outro + v_frete).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns_nfe}CFOP").text.replace(".", "")
            
            categoria = "OUTROS"
            if is_o_emissor_alvo and tp_nf == "1":
                if cfop not in CFOPS_EXCLUSAO_DAS and cfop not in CFOPS_DEVOLUCAO_VENDA:
                    categoria = "RECEITA BRUTA"
            
            if cfop in CFOPS_DEVOLUCAO_VENDA:
                if (is_o_emissor_alvo and tp_nf == "0") or (is_o_destinatario_alvo and tp_nf == "1"):
                    categoria = "DEVOLUÇÃO VENDA"

            regs.append({
                "Unidade_CNPJ": emit_cnpj if is_o_emissor_alvo else dest_cnpj,
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, 
                "Emitente": emit_cnpj, "Destinatario": dest_cnpj,
                "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "V_Contabil": v_contabil, "V_ST": v_st,
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
    st.title("🛡️ Sentinela Ecosystem - Auditoria BR Standard")
    
    if 'reset_key' not in st.session_state: st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente Auditado")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ ALVO", key=f"c_{st.session_state.reset_key}"))
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 Total", value="", key=f"r_{st.session_state.reset_key}")
        rbt12_clean = rbt12_raw.replace(".", "").replace(",", ".")
        rbt12 = Decimal(rbt12_clean) if rbt12_clean else Decimal("0")
        
        if st.button("🗑️ Resetar Tudo"):
            st.session_state.reset_key += 1
            st.rerun()

    c_up1, c_up2 = st.columns(2)
    with c_up1:
        f_norm = st.file_uploader("Movimentação", accept_multiple_files=True, type=["xml", "zip"], key=f"f1_{st.session_state.reset_key}")
    with c_up2:
        f_canc = st.file_uploader("Canceladas", accept_multiple_files=True, type=["xml", "zip"], key=f"f2_{st.session_state.reset_key}")

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_cli:
            st.error("Informe o CNPJ."); return

        ch_canc = set()
        for f in f_canc:
            ch_canc.update(processar_recursivo_generic(f.read(), extrair_chaves_cancelamento))

        ch_vistas, regs = set(), []
        for f in f_norm:
            regs.extend(processar_recursivo_generic(f.read(), extrair_dados_xml, chaves_vistas=ch_vistas, cnpj_cliente=cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(ch_canc)
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), ['V_Contabil', 'V_ST', 'Base_DAS']] = Decimal("0")

            st.subheader("📊 Resumo de Continuidade")
            res_series = df.groupby(['Unidade_CNPJ', 'Tipo', 'Modelo', 'Série']).agg(
                Nota_Inicial=('Nota', 'min'),
                Nota_Final=('Nota', 'max'),
                Qtd=('Nota', 'nunique')
            ).reset_index()
            st.table(res_series)

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
            if not df_f.empty:
                res_fisc = df_f.apply(lambda r: calcular_aliq_efetiva(r, rbt12), axis=1, result_type='expand')
                df_f['Base_F'], df_f['Aliq_F'], df_f['DAS'] = res_fisc[0], res_fisc[1], res_fisc[2]

                st.subheader("📑 Memorial Analítico")
                resumo = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'V_Contabil': 'sum', 'Base_F': 'sum', 'DAS': 'sum'}).reset_index()
                resumo['Aliq_Ef (%)'] = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria'])['Aliq_F'].first().values
                
                # APLICAÇÃO DA FORMATAÇÃO BRASILEIRA
                resumo['Aliq_Ef (%)'] = resumo['Aliq_Ef (%)'].apply(fmt_aliq)
                resumo['V_Contabil'] = resumo['V_Contabil'].apply(fmt_br)
                resumo['Base_F'] = resumo['Base_F'].apply(fmt_br)
                resumo['DAS'] = resumo['DAS'].apply(fmt_br)
                
                st.table(resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq_Ef (%)', 'V_Contabil', 'Base_F', 'DAS']])

                st.markdown("---")
                m1, m2, m3 = st.columns(3)
                m1.metric("Bruto Tributável", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_F'].sum())}")
                m2.metric("(-) Devoluções", f"R$ {fmt_br(abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_F'].sum()))}")
                m3.metric("DAS Final", f"R$ {fmt_br(df_f['DAS'].sum())}")
            
            st.subheader("📋 Auditoria Detalhada")
            df_view = df.copy()
            df_view['V_Contabil'] = df_view['V_Contabil'].apply(fmt_br)
            df_view['Base_DAS'] = df_view['Base_DAS'].apply(fmt_br)
            st.dataframe(df_view[['Nota', 'CFOP', 'Emitente', 'Destinatario', 'Categoria', 'Tipo', 'V_Contabil', 'Base_DAS', 'Cancelada']], use_container_width=True)
        else: st.error("Nenhuma nota encontrada.")

if __name__ == "__main__": main()
