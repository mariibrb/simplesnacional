"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Conciliação Analítica para conferência com PGDAS (Juarez Almeida)
"""

import zipfile
import io
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP
import streamlit as st
import pandas as pd

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

# ─── REGRAS FISCAIS (ANEXO I - COMÉRCIO) ─────────────────────────────────────
# Percentual de ICMS na repartição da 2ª faixa do Anexo I é 34%
PERC_ICMS_ANEXO_I = Decimal("0.34")

# ─── PROCESSAMENTO XML ───────────────────────────────────────────────────────

def extrair_dados_xml(conteudo, chaves_vistas):
    regs = []
    try:
        root = ET.fromstring(conteudo.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text # 1=Saída, 0=Entrada
        
        regs.append({
            "Nota": n_nota,
            "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
            "Valor (vNF)": v_nf,
            "Chave": chave
        })
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Memorial de Cálculo Analítico")
    
    with st.sidebar:
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("Faturamento Acumulado (RBT12)", value="", placeholder="Ex: 256852.76")
        
        try:
            rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0.00")
        except: rbt12 = Decimal("0.00")
        
        st.info("Configurado para: Anexo I (Comércio)")
        is_st = st.toggle("Dedução de ICMS ST (34%)", value=True)

    # ─── CÁLCULO DA ALÍQUOTA (FAIXA 2) ───────────────────────────────────────
    # Alíquota Nominal: 7,30% | Parcela a Deduzir: R$ 5.940,00
    aliq_nom = Decimal("0.073")
    deducao = Decimal("5940.00")
    
    if rbt12 > 0:
        aliq_efetiva_cheia = ((rbt12 * aliq_nom) - deducao) / rbt12
    else:
        aliq_efetiva_cheia = Decimal("0.04") # Faixa 1 default

    # Aplicação da Dedução ST (ICMS)
    aliq_apuracao = aliq_efetiva_cheia
    if is_st:
        aliq_apuracao = aliq_efetiva_cheia * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
    
    aliq_apuracao = aliq_apuracao.quantize(Decimal("0.000001"), ROUND_HALF_UP)

    # ─── DASHBOARD DE TOTAIS ─────────────────────────────────────────────────
    files = st.file_uploader("Upload XMLs para Auditoria", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas))
        
        if registros:
            df = pd.DataFrame(registros)
            fat_bruto = df[df["Tipo"] == "SAÍDA"]["Valor (vNF)"].sum()
            dev_bruto = df[df["Tipo"] == "ENTRADA"]["Valor (vNF)"].sum()
            base_liquida = max(fat_bruto - dev_bruto, Decimal("0.00"))
            
            valor_das = (base_liquida * aliq_apuracao).quantize(Decimal("0.01"), ROUND_HALF_UP)

            st.markdown("### 📊 Dashboard de Conciliação")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Faturamento (vNF)", f"R$ {fat_bruto:,.2f}")
            c2.metric("Base Líquida", f"R$ {base_liquida:,.2f}")
            c3.metric("Alíquota Aplicada", f"{aliq_apuracao*100:.4f}%")
            c4.metric("DAS CALCULADO", f"R$ {valor_das:,.2f}")

            # ─── MEMORIAL DE CÁLCULO ─────────────────────────────────────────
            st.markdown("### 📝 Memorial de Cálculo Detalhado")
            
            with st.container():
                st.markdown(f"""
                <div class="memorial-box">
                    <b>1. DETERMINAÇÃO DA ALÍQUOTA (PGDAS PÁGINA 1)</b><br>
                    • RBT12 (Últimos 12 meses): <span class="highlight">R$ {rbt12:,.2f}</span><br>
                    • Alíquota Nominal (Anexo I - Faixa 2): 7,30%<br>
                    • Parcela a Deduzir: R$ 5.940,00<br>
                    • Alíquota Efetiva Cheia: (({rbt12} * 0,073) - 5940) / {rbt12} = <b>{aliq_efetiva_cheia*100:.4f}%</b><br><br>
                    
                    <b>2. AJUSTE DE SUBSTITUIÇÃO TRIBUTÁRIA (ICMS ST)</b><br>
                    • Percentual de ICMS na Repartição: 34,00%<br>
                    • Alíquota Final (Sem ICMS): {aliq_efetiva_cheia*100:.4f}% * (1 - 0,34) = <span class="highlight">{aliq_apuracao*100:.4f}%</span><br><br>
                    
                    <b>3. CONSOLIDAÇÃO DA BASE DE CÁLCULO (XML)</b><br>
                    • Soma das Notas de Saída (vNF): R$ {fat_bruto:,.2f}<br>
                    • (-) Soma das Devoluções: R$ {dev_bruto:,.2f}<br>
                    • <b>Base de Cálculo Líquida: R$ {base_liquida:,.2f}</b><br><br>
                    
                    <b>4. APURAÇÃO FINAL</b><br>
                    • R$ {base_liquida:,.2f} * {aliq_apuracao*100:.4f}% = <span class="highlight" style="font-size: 20px;">R$ {valor_das:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)

            # ─── LISTAGEM PARA CONFERÊNCIA ───────────────────────────────────
            st.markdown("### 📋 Rastreabilidade nota a nota")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
