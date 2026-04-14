"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Ajuste Finíssimo: Cálculo de DAS sem arredondamento de base intermediária.
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão de 50 casas para garantir que o motor de cálculo seja infalível
getcontext().prec = 50 

# ─── ESTILIZAÇÃO RIHANNA / MONTSERRAT ────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS UNIVERSAIS ───────────────────────────────────────────────
PERC_ICMS_ANEXO_I = Decimal("0.34")
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

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
        if cnpj_cliente and emit_cnpj != cnpj_cliente:
            return []
            
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 

        itens_nota = []
        v_prod_total_nota = Decimal("0")
        
        for det in inf.findall(f"{ns}det"):
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cf = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            itens_nota.append({"cfop": cf, "valor": v_p})
            v_prod_total_nota += v_p

        # ATENÇÃO: Mantendo o Valor Proporcional com precisão total (sem quantize aqui!)
        for item in itens_nota:
            proporcao = item['valor'] / v_prod_total_nota if v_prod_total_nota > 0 else Decimal("0")
            valor_proporcional_cru = v_nf * proporcao
            
            regs.append({
                "Nota": n_nota,
                "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
                "CFOP": item['cfop'],
                "ST": item['cfop'] in CFOPS_ST,
                "Valor Cru": valor_proporcional_cru,
                "Chave": chave
            })
            
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE E MOTOR DE CÁLCULO ───────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Ajuste Finíssimo de DAS")
    
    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        rbt12_raw = st.text_input("Faturamento RBT12", value="504.403,47")
        try:
            rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")
        except: rbt12 = Decimal("0")
        
        is_st_toggle = st.toggle("Dedução ICMS ST (34%)", value=True)

    # Cálculo das alíquotas com precisão extrema
    aliq_nom, deducao = Decimal("0.073"), Decimal("5940.00")
    if rbt12 > 0:
        aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
        aliq_st = aliq_efetiva * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
    else:
        aliq_efetiva = Decimal("0.04")
        aliq_st = aliq_efetiva

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial de Precisão") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            df_saida = df[df["Tipo"] == "SAÍDA"].copy()
            
            # CÁLCULO DO DAS: Usando a base sem arredondamento e alíquota cheia
            df_saida['Aliq'] = df_saida['ST'].apply(lambda x: aliq_st if is_st_toggle and x else aliq_efetiva)
            # O quantize final é APENAS no imposto apurado
            df_saida['DAS'] = df_saida.apply(lambda r: (r['Valor Cru'] * r['Aliq']).quantize(Decimal("0.01"), ROUND_HALF_UP), axis=1)

            st.markdown("### 📊 Dashboard")
            c1, c2, c3 = st.columns(3)
            # Soma total para conferência (apenas exibição formatada)
            total_faturamento = df_saida["Valor Cru"].sum().quantize(Decimal("0.01"), ROUND_HALF_UP)
            c1.metric("Faturamento Total (vNF)", f"R$ {total_faturamento:,.2f}")
            c2.metric("DAS Total Apurado", f"R$ {df_saida['DAS'].sum():,.2f}")
            c3.metric("Alíquota Efetiva", f"{aliq_efetiva*100:.13f}%")

            # RESUMO ANALÍTICO POR CFOP
            st.markdown("### 📑 Resumo por CFOP")
            resumo = df_saida.groupby(['CFOP', 'ST']).agg({'Valor Cru': 'sum', 'DAS': 'sum'}).reset_index()
            # Arredondamos apenas para a visualização da tabela
            resumo['Faturamento Final'] = resumo['Valor Cru'].apply(lambda x: x.quantize(Decimal("0.01"), ROUND_HALF_UP))
            resumo['Alíquota Aplicada'] = resumo['ST'].apply(lambda x: f"{aliq_st*100:.13f}%" if x else f"{aliq_efetiva*100:.13f}%")
            
            st.table(resumo[['CFOP', 'Faturamento Final', 'Alíquota Aplicada', 'DAS']])

            st.markdown("### 📋 Rastreabilidade")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Notas não encontradas para o CNPJ {cnpj_cli}.")

if __name__ == "__main__":
    main()
