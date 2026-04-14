"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Ajuste de Alíquota Real: Foco em bater com o PGDAS (Juarez/Nascel)
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão extrema para bater com o PGDAS
getcontext().prec = 60 

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

# ─── REGRAS FISCAIS ──────────────────────────────────────────────────────────
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}

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

        # Proporcionalidade para manter o vNF intacto na segregação de CFOP
        itens_nota = []
        v_prod_total_nota = Decimal("0")
        for det in inf.findall(f"{ns}det"):
            v_p = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cf = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            itens_nota.append({"cfop": cf, "valor": v_p})
            v_prod_total_nota += v_p

        for item in itens_nota:
            proporcao = item['valor'] / v_prod_total_nota if v_prod_total_nota > 0 else Decimal("0")
            regs.append({
                "Nota": n_nota, "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
                "CFOP": item['cfop'], "ST": item['cfop'] in CFOPS_ST,
                "Valor Cru": v_nf * proporcao, "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def main():
    st.title("🛡️ Sentinela - Auditoria com Alíquota Editável")
    
    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_cli = limpar_cnpj(st.text_input("CNPJ", value="52.980.554/0001-04"))
        
        st.header("⚙️ Configuração de Alíquotas")
        st.caption("Ajuste aqui para bater com o PGDAS")
        
        # Inputs Manuais de Alíquota (Em % como no PGDAS)
        aliq_ef_manual = st.text_input("Alíquota Efetiva Normal (%)", value="6.7522285896211")
        aliq_st_manual = st.text_input("Alíquota ICMS ST (%)", value="4.4564708691500")

        try:
            aliq_efetiva = Decimal(aliq_ef_manual.replace(",", ".")) / 100
            aliq_st = Decimal(aliq_st_manual.replace(",", ".")) / 100
        except:
            st.error("Erro no formato da alíquota. Use pontos.")
            aliq_efetiva = Decimal("0")
            aliq_st = Decimal("0")

    files = st.file_uploader("Upload XMLs", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial Analítico") and files:
        chaves_vistas, registros = set(), []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            df_saida = df[df["Tipo"] == "SAÍDA"].copy()
            
            # Agrupamento para consolidar faturamento por CFOP
            resumo = df_saida.groupby(['CFOP', 'ST']).agg({'Valor Cru': 'sum'}).reset_index()
            
            def aplicar_imposto(row):
                # Arredonda a base para 2 casas antes da conta final conforme regra fiscal
                base = row['Valor Cru'].quantize(Decimal("0.01"), ROUND_HALF_UP)
                aliq = aliq_st if row['ST'] else aliq_efetiva
                return (base * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)

            resumo['DAS'] = resumo.apply(aplicar_imposto, axis=1)
            resumo['Faturamento'] = resumo['Valor Cru'].apply(lambda x: x.quantize(Decimal("0.01"), ROUND_HALF_UP))
            resumo['Aliq_View'] = resumo['ST'].apply(lambda x: f"{aliq_st*100:.13f}%" if x else f"{aliq_efetiva*100:.13f}%")

            st.markdown("### 📊 Dashboard de Apuração")
            c1, c2, c3 = st.columns(3)
            c1.metric("Faturamento Total", f"R$ {resumo['Faturamento'].sum():,.2f}")
            c2.metric("DAS Total", f"R$ {resumo['DAS'].sum():,.2f}")
            c3.metric("Alíquota Normal", f"{aliq_efetiva*100:.4f}%")

            st.markdown("### 📑 Resumo Analítico por CFOP")
            st.table(resumo[['CFOP', 'Faturamento', 'Aliq_View', 'DAS']])
            
            st.markdown("### 📋 Rastreabilidade")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error("Nenhuma nota encontrada para o CNPJ informado.")

if __name__ == "__main__":
    main()
