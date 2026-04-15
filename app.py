"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo (VERSÃO INTEGRAL - CORREÇÃO DE SOMA)
Foco: PGDAS Anexos I e II, Faixas 1-6, Rigor de Identidade de CNPJ e Estilo Rihanna
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

# Grupos de CFOPs para blindagem fiscal
CFOPS_VENDA = {"5101", "5102", "5103", "5105", "5106", "5401", "5403", "5405", "6101", "6102", "6103", "6105", "6106", "6401", "6403", "6404"}
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
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")
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

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
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
        
        is_o_emissor_alvo = (emit_cnpj == cnpj_cliente)
        is_o_destinatario_alvo = (dest_cnpj == cnpj_cliente)

        # Se o CNPJ auditado não participa da nota, ignora
        if not (is_o_emissor_alvo or is_o_destinatario_alvo): return []
            
        ide = inf.find(f"{ns}ide")
        n_nota, serie, modelo = int(ide.find(f"{ns}nNF").text), ide.find(f"{ns}serie").text, ide.find(f"{ns}mod").text
        tp_nf = ide.find(f"{ns}tpNF").text 

        for det in inf.findall(f"{ns}det"):
            prod, impo = det.find(f"{ns}prod"), det.find(f"{ns}imposto")
            v_p = Decimal(prod.find(f"{ns}vProd").text)
            v_desc = Decimal(prod.find(f"{ns}vDesc").text) if prod.find(f"{ns}vDesc") is not None else Decimal("0")
            v_outro = Decimal(prod.find(f"{ns}vOutro").text) if prod.find(f"{ns}vOutro") is not None else Decimal("0")
            v_frete = Decimal(prod.find(f"{ns}vFrete").text) if prod.find(f"{ns}vFrete") is not None else Decimal("0")
            
            v_st, v_ipi = Decimal("0"), Decimal("0")
            icms = impo.find(f".//{ns}ICMS")
            if icms is not None:
                vst = icms.find(f".//{ns}vICMSST")
                if vst is not None: v_st = Decimal(vst.text)
            ipi = impo.find(f".//{ns}IPI")
            if ipi is not None:
                vipi = ipi.find(f".//{ns}vIPI")
                if vipi is not None: v_ipi = Decimal(vipi.text)

            v_contabil = (v_p + v_ipi + v_st + v_outro + v_frete - v_desc).quantize(Decimal("0.01"), ROUND_HALF_UP)
            base_das = (v_p - v_desc + v_outro + v_frete).quantize(Decimal("0.01"), ROUND_HALF_UP)
            cfop = prod.find(f"{ns}CFOP").text.replace(".", "")
            
            categoria = "OUTROS"
            # REGRA DE RECEITA BRUTA: Deve ser Emissor e Saída (1)
            if is_o_emissor_alvo and tp_nf == "1":
                if cfop in CFOPS_VENDA and cfop not in CFOPS_EXCLUSAO_SOMA:
                    categoria = "RECEITA BRUTA"
            
            # REGRA DE DEVOLUÇÃO: Minha Entrada própria OU Saída de Terceiro contra mim
            if cfop in CFOPS_DEVOL_VEN_PROPRIA or cfop in CFOPS_DEVOL_VEN_TERCEIRO:
                if (is_o_emissor_alvo and tp_nf == "0") or (is_o_destinatario_alvo and tp_nf == "1"):
                    categoria = "DEVOLUÇÃO VENDA"

            regs.append({
                "Unidade_CNPJ": emit_cnpj if is_o_emissor_alvo else dest_cnpj,
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "CFOP": cfop, "ST": cfop in CFOPS_ST, "Anexo": "ANEXO II" if cfop in CFOPS_INDUSTRIA else "ANEXO I",
                "V_Contabil": v_contabil, "V_ST": v_st, "V_IPI": v_ipi,
                "Base_DAS": base_das, "Tipo": "SAÍDA" if tp_nf == "1" else "ENTRADA",
                "Categoria": categoria, "Chave": chave, "Emitente": emit_cnpj, "Destinatário": dest_cnpj
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
    st.title("🛡️ Sentinela Ecosystem - Auditoria PGDAS")
    
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

    c1, c2 = st.columns(2)
    with c1: f_norm = st.file_uploader("Movimentação", accept_multiple_files=True, type=["xml", "zip"])
    with c2: f_canc = st.file_uploader("Canceladas", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria") and f_norm:
        if not cnpj_cli:
            st.error("Informe o CNPJ."); return

        ch_canc = set()
        for f in f_canc: ch_canc.update(processar_recursivo_generic(f.read(), extrair_chaves_cancelamento))

        ch_vistas, regs = set(), []
        for f in f_norm: regs.extend(processar_recursivo_generic(f.read(), extrair_dados_xml, chaves_vistas=ch_vistas, cnpj_cliente=cnpj_cli))
        
        if regs:
            df = pd.DataFrame(regs)
            df['Cancelada'] = df['Chave'].isin(ch_canc)
            
            # Zera faturamento de canceladas ou categoria OUTROS
            df.loc[df['Cancelada'] | (df['Categoria'] == "OUTROS"), ['V_Contabil', 'V_ST', 'Base_DAS']] = Decimal("0")

            st.subheader("📊 Resumo de Continuidade (Somente Base Ativa)")
            df_cont = df[(df['Categoria'].isin(["RECEITA BRUTA", "DEVOLUÇÃO VENDA"])) & (~df['Cancelada'])].copy()
            if not df_cont.empty:
                res_series = df_cont.groupby(['Unidade_CNPJ', 'Categoria', 'Modelo', 'Série']).agg(Nota_Ini=('Nota', 'min'), Nota_Fim=('Nota', 'max'), Qtd=('Nota', 'nunique')).reset_index()
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

                st.subheader("📑 Memorial Analítico (13 Casas)")
                resumo = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria']).agg({'V_Contabil': 'sum', 'Base_F': 'sum', 'DAS': 'sum'}).reset_index()
                resumo['Aliq_Ef'] = df_f.groupby(['Anexo', 'CFOP', 'ST', 'Categoria'])['Aliq_F'].first().values
                resumo['Aliq (%)'] = resumo['Aliq_Ef'].apply(fmt_aliq)
                resumo['Contabil'] = resumo['V_Contabil'].apply(fmt_br)
                resumo['Base PGDAS'] = resumo['Base_F'].apply(fmt_br)
                resumo['Imposto DAS'] = resumo['DAS'].apply(fmt_br)
                st.table(resumo[['Anexo', 'CFOP', 'ST', 'Categoria', 'Aliq (%)', 'Contabil', 'Base PGDAS', 'Imposto DAS']])

                st.markdown("---")
                m1, m2, m3 = st.columns(3)
                m1.metric("Bruto Tributável", f"R$ {fmt_br(df_f[df_f['Categoria']=='RECEITA BRUTA']['Base_F'].sum())}")
                m2.metric("(-) Devoluções Válidas", f"R$ {fmt_br(abs(df_f[df_f['Categoria']=='DEVOLUÇÃO VENDA']['Base_F'].sum()))}")
                m3.metric("DAS Final", f"R$ {fmt_br(df_f['DAS'].sum())}")
            
            st.subheader("📋 Auditoria Detalhada (Log de Emitentes)")
            df_view = df.copy()
            df_view['V_Contabil'] = df_view['V_Contabil'].apply(fmt_br)
            df_view['Base_DAS'] = df_view['Base_DAS'].apply(fmt_br)
            st.dataframe(df_view[['Nota', 'CFOP', 'Emitente', 'Destinatário', 'Categoria', 'V_Contabil', 'Base_DAS', 'Cancelada']], use_container_width=True)
        else: st.error("Nenhuma nota encontrada com o CNPJ alvo informado.")

if __name__ == "__main__": main()
