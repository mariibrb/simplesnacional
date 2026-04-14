import zipfile
import io
import re
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, getcontext
import streamlit as st
import pandas as pd

# Precisão extrema para bater com o PGDAS (13 casas)
getcontext().prec = 30 

# ─── ESTILO RIHANNA / MONTSERRAT ─────────────────────────────────────────────
st.set_page_config(page_title="Sentinela Ecosystem - Auditoria", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        html, body, [class*="css"] { font-family: 'Montserrat', sans-serif; }
        .stApp { background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%); color: #4a0024; }
        h1, h2, h3, h4 { color: #d81b60 !important; font-weight: 800; }
        .stMetric { background-color: rgba(255, 255, 255, 0.7); padding: 15px; border-radius: 10px; border-left: 5px solid #d81b60; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .memorial-box { background-color: white; padding: 25px; border-radius: 10px; border: 1px solid #d81b60; color: black; line-height: 1.6; }
        .highlight { color: #d81b60; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ─── REGRAS FISCAIS (ANEXO I) ────────────────────────────────────────────────
TABELAS_SIMPLES = [
    (1, Decimal("0.00"), Decimal("180000.00"), Decimal("0.04"), Decimal("0.00"), Decimal("0.3350")),
    (2, Decimal("180000.01"), Decimal("360000.00"), Decimal("0.073"), Decimal("5940.00"), Decimal("0.3400")),
    (3, Decimal("360000.01"), Decimal("720000.00"), Decimal("0.095"), Decimal("13860.00"), Decimal("0.3350")),
]
CFOPS_ST = {"5401", "5403", "5405", "5603", "6401", "6403", "6404"}
CFOPS_DEVOLUCAO = {"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"}

# ─── FUNÇÕES DE AUDITORIA ────────────────────────────────────────────────────

def limpar_cnpj(cnpj):
    return re.sub(r'\D', '', str(cnpj))

def extrair_dados_xml(conteudo, chaves_vistas, cnpj_cliente):
    regs = []
    try:
        xml_str = conteudo.decode('utf-8', errors='ignore')
        xml_str = re.sub(r'^.*<\?xml', '<?xml', xml_str, flags=re.DOTALL)
        root = ET.fromstring(xml_str.lstrip())
        ns = "{http://www.portalfiscal.inf.br/nfe}"
        
        inf = root.find(f".//{ns}infNFe")
        if inf is None: return []
        
        chave = inf.attrib.get('Id', '')[3:]
        if not chave or chave in chaves_vistas: return []
        
        emit_node = inf.find(f"{ns}emit/{ns}CNPJ")
        emit_cnpj = limpar_cnpj(emit_node.text) if emit_node is not None else ""
        
        # Filtro de CNPJ inteligente
        if cnpj_cliente and emit_cnpj != cnpj_cliente:
            return []

        n_nota = int(inf.find(f"{ns}ide/{ns}nNF").text)
        tipo_op = inf.find(f"{ns}ide/{ns}tpNF").text # 1=Saída, 0=Entrada

        for det in inf.findall(f"{ns}det"):
            v_prod = Decimal(det.find(f"{ns}prod/{ns}vProd").text)
            cfop = det.find(f"{ns}prod/{ns}CFOP").text.replace(".", "")
            csosn = det.find(f".//{ns}CSOSN")
            
            # Identifica ST pelo CFOP ou CSOSN 500
            is_st = (csosn is not None and csosn.text == "500") or cfop in CFOPS_ST
            
            regs.append({
                "Nota": n_nota,
                "Tipo": "SAÍDA" if tipo_op == "1" else "DEVOLUÇÃO",
                "CFOP": cfop,
                "Valor Tributável": v_prod, # FOCO NO VALOR DO PRODUTO, NÃO DA NOTA
                "ST": is_st,
                "Chave": chave
            })
        chaves_vistas.add(chave)
    except: pass
    return regs

# ─── INTERFACE ───────────────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Auditoria com Faturamento de Itens")
    
    with st.sidebar:
        st.header("👤 Cliente")
        cnpj_input = st.text_input("CNPJ do Cliente", value="52.980.554/0001-04")
        cnpj_cli = limpar_cnpj(cnpj_input)
        
        st.header("⚙️ PGDAS")
        rbt12_raw = st.text_input("RBT12 Acumulado", value="504.403,47")
        rbt12 = Decimal(rbt12_raw.replace(".", "").replace(",", ".")) if rbt12_raw else Decimal("0")

    files = st.file_uploader("Upload XML ou ZIP", accept_multiple_files=True, type=["xml", "zip"])

    if st.button("🚀 Iniciar Auditoria"):
        chaves_vistas = set()
        bytes_list = []
        
        for f in files:
            content = f.read()
            if f.name.lower().endswith('.zip'):
                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    for n in z.namelist():
                        bytes_list.append(z.read(n))
            else:
                bytes_list.append(content)

        registros = []
        for b in bytes_list:
            registros.extend(extrair_dados_xml(b, chaves_vistas, cnpj_cli))
        
        if registros:
            df = pd.DataFrame(registros)
            
            # Cálculo de Alíquotas Dinâmico (13 casas)
            aliq_nom, ded, f_n, p_icms = Decimal("0.095"), Decimal("13860.00"), 3, Decimal("0.335")
            for num, ini, fim, nom, d_val, p_val in TABELAS_SIMPLES:
                if rbt12 <= fim:
                    f_n, aliq_nom, ded, p_icms = num, nom, d_val, p_val
                    break
            
            aliq_ef = ((rbt12 * aliq_nom) - ded) / rbt12 if rbt12 > 0 else aliq_nom
            aliq_ef = aliq_ef.quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            aliq_st = (aliq_ef * (Decimal("1.0") - p_icms)).quantize(Decimal("0.0000000000000001"), ROUND_HALF_UP)
            
            # Totais Analíticos
            receita_bruta_total = df[df['Tipo'] == "SAÍDA"]['Valor Tributável'].sum()
            receita_st = df[(df['Tipo'] == "SAÍDA") & (df['ST'] == True)]['Valor Tributável'].sum()
            receita_normal = receita_bruta_total - receita_st
            
            # Resumo CFOP
            resumo = []
            for cfop in df['CFOP'].unique():
                sub = df[df['CFOP'] == cfop]
                v_bruto = sub['Valor Tributável'].sum()
                st_flag = sub['ST'].any()
                tp = sub['Tipo'].iloc[0]
                
                # Alíquota específica
                aliq = aliq_st if st_flag else (Decimal("0") if tp == "DEVOLUÇÃO" else aliq_ef)
                imp = (v_bruto * aliq).quantize(Decimal("0.01"), ROUND_HALF_UP)
                
                resumo.append({"CFOP": cfop, "Tipo": tp, "Faturamento": v_bruto, "Alíquota": f"{aliq*100:.13f}%", "Imposto": imp})

            st.markdown("### 📊 Dashboard de Faturamento Real")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Receita Bruta Total", f"R$ {receita_bruta_total:,.2f}")
            c2.metric("Receita Normal", f"R$ {receita_normal:,.2f}")
            c3.metric("Receita ICMS ST", f"R$ {receita_st:,.2f}")
            c4.metric("DAS TOTAL", f"R$ {sum(r['Imposto'] for r in resumo):,.2f}")

            st.table(pd.DataFrame(resumo))
            st.dataframe(df.sort_values("Nota"), use_container_width=True)
        else:
            st.error("Nenhuma nota tributável encontrada para o CNPJ informado.")

if __name__ == "__main__":
    main()
