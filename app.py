"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Conciliação Analítica com Divisão/Trava de CNPJ
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

# ─── REGRAS FISCAIS (ANEXO I - COMÉRCIO) ─────────────────────────────────────
PERC_ICMS_ANEXO_I = Decimal("0.34")

# ─── FUNÇÕES DE APOIO ────────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    """Remove caracteres não numéricos para comparação segura."""
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
        
        # Leitura do Emitente para trava de CNPJ
        emit_cnpj = limpar_cnpj(inf.find(f"{ns}emit/{ns}CNPJ").text)
        
        # TRAVA DE CNPJ: Se o usuário definiu um CNPJ, ignora notas de terceiros
        if cnpj_cliente and emit_cnpj != cnpj_cliente:
            return []
            
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
        st.header("👤 Identificação")
        cnpj_input = st.text_input("CNPJ do Cliente (Trava de Segurança)", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ Parâmetros PGDAS")
        rbt12_raw = st.text_input("Faturamento Acumulado (RBT12)", value="", placeholder="Ex: 504403.47")
        
        try:
            rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0.00")
        except: rbt12 = Decimal("0.00")
        
        st.info("Configurado para: Anexo I (Comércio)")
        is_st = st.toggle("Dedução de ICMS ST (34%)", value=True)

    # ─── CÁLCULO DA ALÍQUOTA (DINÂMICO) ──────────────────────────────────────
    aliq_nom = Decimal("0.073")
    deducao = Decimal("5940.00")
    
    if rbt12 > 0:
        aliq_efetiva_cheia = ((rbt12 * aliq_nom) - deducao) / rbt12
    else:
        aliq_efetiva_cheia = Decimal("0.04")

    aliq_apuracao = aliq_efetiva_cheia
    if is_st:
        aliq_apuracao = aliq_efetiva_cheia * (Decimal("1.0") - PERC_ICMS_ANEXO_I)
    
    aliq_apuracao = aliq_apuracao.quantize(Decimal("0.000001"), ROUND_HALF_UP)

    # ─── PROCESSAMENTO ───────────────────────────────────────────────────────
    files = st.file_uploader("Upload XMLs para Auditoria", accept_multiple_files=True, type=["xml"])

    if st.button("🚀 Gerar Memorial") and files:
        chaves_vistas = set()
        registros = []
        for f in files:
            registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
        
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
            st.markdown(f"""
                <div class="memorial-box">
                    <b>1. DETERMINAÇÃO DA ALÍQUOTA (CNPJ: {cnpj_cli})</b><br>
                    • RBT12: <span class="highlight">R$ {rbt12:,.2f}</span><br>
                    • Alíquota Nominal: 7,30% | Parcela a Deduzir: R$ 5.940,00<br>
                    • Alíquota Efetiva: {aliq_efetiva_cheia*100:.4f}%<br><br>
                    
                    <b>2. AJUSTE DE SUBSTITUIÇÃO TRIBUTÁRIA</b><br>
                    • Dedução ICMS (34%): <span class="highlight">{aliq_apuracao*100:.4f}%</span><br><br>
                    
                    <b>3. CONSOLIDAÇÃO DA BASE</b><br>
                    • Saídas: R$ {fat_bruto:,.2f} | Entradas: R$ {dev_bruto:,.2f}<br>
                    • <b>Base Líquida: R$ {base_liquida:,.2f}</b><br><br>
                    
                    <b>4. APURAÇÃO FINAL</b><br>
                    • R$ {base_liquida:,.2f} * {aliq_apuracao*100:.4f}% = <span class="highlight" style="font-size: 20px;">R$ {valor_das:,.2f}</span>
                </div>
            """, unsafe_allow_html=True)

            st.markdown("### 📋 Rastreabilidade nota a nota")
            st.dataframe(df.sort_values("Nota"), use_container_width=True, hide_index=True)
        else:
            st.error(f"❌ Nenhuma nota do CNPJ {cnpj_cli} foi encontrada nos arquivos enviados.")

if __name__ == "__main__":
    main()
