"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Conciliação Analítica com Divisão por CFOP e ST
"""

import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão extrema para bater com o PGDAS
getcontext().prec = 30 

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
# Percentual de ICMS na repartição (Anexo I)
PERC_REPARTICAO_ICMS = Decimal("0.34")

# CFOPs que indicam Substituição Tributária (conforme Seção II do PGDAS)
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

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
        
        # Validação de CNPJ do Emitente
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        dest_node = inf.find(f"{ns}dest/{ns}CNPJ")
        dest_cnpj = limpar_cnpj(dest_node.text) if dest_node is not None else ""
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text # 1=Saída, 0=Entrada

        # Processamento de Saídas (Faturamento do Cliente)
        if emit_cnpj == cnpj_cliente and tipo_op == "1":
            for det in inf.findall(f"{ns}det"):
                v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                csosn = det.find(f".//{ns}CSOSN")
                
                # Regra: ST se CSOSN for 500 ou CFOP estiver na lista de ST
                is_st = (csosn is not None and csosn.text == "500") or cfop in CFOPS_ST
                
                regs.append({
                    "Nota": n_nota, "Tipo": "SAÍDA", "CFOP": cfop, 
                    "Valor": v_prod, "ST": is_st, "Chave": chave
                })
            chaves_vistas.add(chave)

        # Processamento de Entradas (Devoluções ao Cliente)
        elif dest_cnpj == cnpj_cliente and tipo_op == "0":
            for det in inf.findall(f"{ns}det"):
                cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
                if cfop in CFOPS_DEVOLUCAO:
                    v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
                    regs.append({
                        "Nota": n_nota, "Tipo": "DEVOLUÇÃO", "CFOP": cfop, 
                        "Valor": v_prod, "ST": False, "Chave": chave
                    })
            chaves_vistas.add(chave)
            
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria com Segregação de CFOP")
    
    with st.sidebar:
        st.header("👤 Identificação")
        cnpj_input = st.text_input("CNPJ do Cliente", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("RBT12 (Faturamento 12 meses)", placeholder="Ex: 504403.47")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")

    files = st.file_uploader("Upload XMLs para Auditoria", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            
            # Cálculo de Alíquotas (Com 13 casas decimais de precisão)
            # Exemplo baseado na Faixa 3 (Anexo I)
            aliq_nom, deducao = Decimal("0.095"), Decimal("13860.00")
            
            aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12 if rbt12 > 0 else Decimal("0.04")
            aliq_st = (aliq_efetiva * (Decimal("1.0") - PERC_REPARTICAO_ICMS)).quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            aliq_efetiva = aliq_efetiva.quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            
            # Totalizadores de Lote
            fat_bruto_total = df[df['Tipo'] == "SAÍDA"]['Valor'].sum()
            val_st_total = df[(df['Tipo'] == "SAÍDA") & (df['ST'] == True)]['Valor'].sum()
            dev_total = df[df['Tipo'] == "DEVOLUÇÃO"]['Valor'].sum()

            # Resumo CFOP para o Memorial
            resumo_cfop = []
            for cfop in df['CFOP'].unique():
                sub = df[df['CFOP'] == cfop]
                tipo = sub['Tipo'].iloc[0]
                is_st_item = sub['ST'].any()
                v_bruto_item = sub['Valor'].sum()
                
                # Subtração Real: Deduz ST da base normal se for faturamento
                v_liq_item = v_bruto_item - val_st_total if (not is_st_item and tipo == "SAÍDA") else v_bruto_item
                aliq_item = aliq_st if is_st_item else (Decimal("0") if tipo == "DEVOLUÇÃO" else aliq_efetiva)
                imp_item = (v_liq_item * aliq_item).quantize(Decimal("0.01"), ROUND_HALF_UP)
                
                resumo_cfop.append({
                    "CFOP": cfop, "Tipo": tipo, "ST": is_st_item, 
                    "V. Bruto": v_bruto_item, "Base Líquida": v_liq_item, 
                    "Alíquota": f"{aliq_item*100:.13f}%", "Imposto": imp_item
                })

            # DASHBOARD
            st.markdown("### 📊 Dashboard de Faturamento Real")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faturamento Bruto (vProd)", f"R$ {fat_bruto_total:,.2f}")
            c2.metric("Base Normal Líquida", f"R$ {fat_bruto_total - val_st_total:,.2f}")
            c3.metric("Base ICMS ST", f"R$ {val_st_total:,.2f}")
            c4.metric("DAS TOTAL", f"R$ {sum(r['Imposto'] for r in resumo_cfop):,.2f}")

            # MEMORIAL DETALHADO
            st.markdown("### 📝 Memorial de Cálculo (Resumo por CFOP)")
            st.markdown(f"""
                <div class="memorial-box">
                    <b>DETALHAMENTO TRIBUTÁRIO (CNPJ: {cnpj_cli})</b><br>
                    • Alíquota PGDAS: {aliq_efetiva*100:.13f}%<br>
                    • Alíquota com Abatimento ST: <b>{aliq_st*100:.13f}%</b><br>
                    • <small>Nota: O valor de R$ {val_st_total:,.2f} foi segregado para não incidência de ICMS.</small>
                </div>
            """, unsafe_allow_html=True)
            
            st.table(pd.DataFrame(resumo_cfop))
            
            st.markdown("### 📋 Rastreabilidade nota a nota")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Nenhuma nota autorizada para o CNPJ {cnpj_cli} foi encontrada.")

if __name__ == "__main__":
    main()
