"""
Sentinela Ecosystem - Auditoria e Memorial de Cálculo
Foco: Cálculo Automático de Alíquotas PGDAS (13 Casas) e Base vNF Proporcional
Incluso: Detecção de Intervalo por Série, Modelo e Processamento de Matrioscas
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
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS UNIVERSAIS ──────────────────────────────────────────────
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
    (4, Decimal("720000.01"), Decimal("1800000.00"), Decimal("0.107"), Decimal("22500.00"), Decimal("0.3350")),
]
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
        serie = inf.find(f"{ns}ide/{ns}serie").text
        modelo = inf.find(f"{ns}ide/{ns}mod").text
        v_nf = Decimal(inf.find(f"{ns}total/{ns}ICMSTot/{ns}vNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text 

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
                "Nota": n_nota, "Série": serie, "Modelo": modelo,
                "Tipo": "SAÍDA" if tipo_op == "1" else "ENTRADA",
                "CFOP": item['cfop'], "ST": item['cfop'] in CFOPS_ST,
                "Valor Cru": v_nf * proporcao, "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

def processar_recursivo(arquivo_bytes, chaves_vistas, cnpj_cli):
    registros = []
    try:
        with zipfile.ZipFile(io.BytesIO(arquivo_bytes)) as z:
            for nome in z.namelist():
                if nome.lower().endswith('.xml'):
                    with z.open(nome) as f:
                        registros.extend(extrair_dados_xml(f.read(), chaves_vistas, cnpj_cli))
                elif nome.lower().endswith('.zip'):
                    with z.open(nome) as f:
                        registros.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
    except zipfile.BadZipFile:
        registros.extend(extrair_dados_xml(arquivo_bytes, chaves_vistas, cnpj_cli))
    return registros

# ─── INTERFACE E MOTOR DE CÁLCULO ────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria e Memorial (Anexo I)")
    
    if 'reset_key' not in st.session_state:
        st.session_state.reset_key = 0

    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ", value="", placeholder="CNPJ do Emitente", key=f"cnpj_{st.session_state.reset_key}")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ Receita Bruta")
        rbt12_raw = st.text_input("Faturamento RBT12", value="", placeholder="0,00", key=f"rbt12_{st.session_state.reset_key}")
        
        if rbt12_raw:
            try:
                clean_rbt12 = rbt12_raw.replace(".", "").replace(",", ".")
                rbt12 = Decimal(clean_rbt12)
            except:
                st.error("RBT12 inválido.")
                rbt12 = Decimal("0")
        else:
            rbt12 = Decimal("0")

        if st.button("🗑️ Limpar Tudo"):
            st.session_state.reset_key += 1
            st.cache_data.clear()
            st.rerun()

    # CÁLCULO ALÍQUOTA
    aliq_nom, deducao, p_icms = Decimal("0.04"), Decimal("0"), Decimal("0.335")
    for num, ini, fim, nom, ded, perc_icms in TABELAS_SIMPLES:
        if rbt12 <= fim:
            aliq_nom, deducao, p_icms = nom, ded, perc_icms
            break
            
    if rbt12 > 0:
        aliq_efetiva = ((rbt12 * aliq_nom) - deducao) / rbt12
        aliq_st = aliq_efetiva * (Decimal("1.0") - p_icms)
    else:
        aliq_efetiva = Decimal("0.04")
        aliq_st = aliq_efetiva

    aliq_ef_view = aliq_efetiva.quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
    aliq_st_view = aliq_st.quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)

    files = st.file_uploader("Upload XMLs/ZIPs", accept_multiple_files=True, type=["xml", "zip"], key=f"files_{st.session_state.reset_key}")

    if st.button("🚀 Executar Auditoria") and files:
        if not cnpj_cli:
            st.warning("Informe o CNPJ.")
            return

        chaves_vistas, registros = set(), []
        for f in files:
            registros.extend(processar_recursivo(f.read(), chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            df_saida = df[df["Tipo"] == "SAÍDA"].copy()
            
            if not df_saida.empty:
                st.markdown("### 📊 Dashboard de Intervalos e Faturamento")
                
                # Agrupamento de Intervalos por Série e Modelo
                intervalos = df_saida.groupby(['Modelo', 'Série']).agg(
                    Primeira_Nota=('Nota', 'min'),
                    Ultima_Nota=('Nota', 'max'),
                    Qtd_Notas=('Nota', 'nunique')
                ).reset_index()
                
                # Exibição dos Intervalos
                cols = st.columns(len(intervalos) if len(intervalos) < 5 else 4)
                for i, row in intervalos.iterrows():
                    with cols[i % 4]:
                        st.metric(f"Série {row['Série']} (Mod {row['Modelo']})", 
                                  f"{row['Primeira_Nota']} → {row['Ultima_Nota']}",
                                  f"{row['Qtd_Notas']} notas")

                # Resumo Fiscal
                resumo = df_saida.groupby(['CFOP', 'ST']).agg({'Valor Cru': 'sum'}).reset_index()
                def aplicar_imposto(row):
                    base = row['Valor Cru'].quantize(Decimal("0.01"), ROUND_HALF_UP)
                    aliq = aliq_st if row['ST'] else aliq_efetiva
                    return (base * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)

                resumo['DAS'] = resumo.apply(aplicar_imposto, axis=1)
                resumo['Faturamento'] = resumo['Valor Cru'].apply(lambda x: x.quantize(Decimal("0.01"), ROUND_HALF_UP))
                
                st.markdown("---")
                c1, c2 = st.columns(2)
                c1.metric("Faturamento Total Detectado", f"R$ {resumo['Faturamento'].sum():,.2f}")
                c2.metric("Total DAS Calculado", f"R$ {resumo['DAS'].sum():,.2f}")

                st.markdown("### 📑 Detalhamento por CFOP")
                st.table(resumo[['CFOP', 'Faturamento', 'DAS']])
                
                st.markdown("### 📋 Rastreabilidade Completa")
                st.dataframe(df.sort_values(["Modelo", "Série", "Nota"]), use_container_width=True, hide_index=True)
            else:
                st.warning("Sem notas de saída para este CNPJ.")
        else:
            st.error("Nenhum dado válido extraído.")

if __name__ == "__main__":
    main()
