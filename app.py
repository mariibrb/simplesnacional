"""
Apuração do Simples Nacional - Leitura de XMLs (NF-e modelo 55, CT-e modelo 57, NFC-e modelo 65/42)
Autor: Script gerado conforme especificação fiscal para escritório contábil
Execução: streamlit run app.py
"""

import os
import csv
import zipfile
import logging
import io
import re
from datetime import datetime
from xml.etree import ElementTree as ET
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import streamlit as st
import pdfplumber

# ─── ESTILIZAÇÃO E INTERFACE (Tema Rihanna / Montserrat) ──────────────────────
st.set_page_config(page_title="Apuração Simples Nacional - Sentinela", layout="wide")

st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;400;600;800&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Montserrat', sans-serif;
        }
        
        .stApp {
            background: radial-gradient(circle at top center, #ffe6f0 0%, #ffb3d1 100%);
            color: #4a0024;
        }
        
        h1, h2, h3, h4, h5, h6 {
            color: #d81b60 !important;
            font-weight: 800;
        }
        
        .stButton>button {
            background-color: #d81b60;
            color: white;
            border-radius: 8px;
            border: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .stButton>button:hover {
            background-color: #ad144d;
            box-shadow: 0 4px 12px rgba(216, 27, 96, 0.4);
        }

        .stDownloadButton>button {
            background-color: #c2185b;
            color: white;
        }
        
        .stMetric {
            background-color: rgba(255, 255, 255, 0.7);
            padding: 15px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.05);
            border-left: 5px solid #d81b60;
        }
    </style>
""", unsafe_allow_html=True)

# ─── CONFIGURAÇÕES INICIAIS ───────────────────────────────────────────────────

TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = f"erros_processamento_{TIMESTAMP}.log"
CSV_FILE = f"apuracao_analitica_{TIMESTAMP}.csv"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ─── NAMESPACES PADRÃO SEFAZ ──────────────────────────────────────────────────

NS_NFE = "{http://www.portalfiscal.inf.br/nfe}"
NS_CTE = "{http://www.portalfiscal.inf.br/cte}"

# ─── CFOPs RELEVANTES ─────────────────────────────────────────────────────────

CFOPS_RECEITA_BRUTA = {
    "5101", "5102", "5103", "5104", "5105", "5106", "5109", "5110", "5111",
    "5112", "5113", "5114", "5115", "5116", "5117", "5118", "5119", "5120",
    "5122", "5123", "5124", "5125", "5403", "5405",
    "6101", "6102", "6103", "6104", "6105", "6106", "6107", "6108", "6109",
    "6110", "6111", "6112", "6113", "6114", "6115", "6116", "6117", "6118",
    "6119", "6120", "6122", "6123", "6124", "6125", "6403", "6404", "6405",
    "7101", "7102", "7105", "7106", "7127",
}

CFOPS_DEVOLUCAO_SAIDA = {
    "5201", "5202", "5204", "5206", "5208", "5209", "5210",
    "6201", "6202", "6204", "6206", "6208", "6209", "6210",
}

CFOPS_SAIDA_NAO_RECEITA = {
    "5901", "5902", "5903", "5904", "5905", "5906", "5907", "5908",
    "5909", "5910", "5911", "5912", "5913", "5914", "5915", "5916",
    "5917", "5918", "5919", "5920", "5921", "5922", "5923", "5924",
    "5925", "5929", "5931", "5932", "5933", "5934", "5935", "5936",
    "5937", "5938", "5939", "5940", "5941", "5942", "5943", "5944",
    "5945", "5946", "5947", "5948", "5949",
    "6901", "6902", "6903", "6904", "6905", "6906", "6907", "6908",
    "6909", "6910", "6911", "6912", "6913", "6914", "6915", "6916",
    "6920", "6929",
    "7204", "7205", "7210", "7211",
}

CFOPS_DEVOLUCAO_ENTRADA = {
    "1201", "1202", "1203", "1204", "1205", "1206", "1207",
    "2201", "2202", "2203", "2204", "2205", "2206", "2207",
}

CFOPS_ENTRADA_USO_CONSUMO_ATIVO = {
    "2551", "2552", "2553", "2554", "2555", "2556", "2557",
    "2911", "2912", "2913",
    "1551", "1552", "1553", "1554", "1555", "1556",
}

CFOPS_ENTRADA_COMERCIALIZACAO = {
    "2101", "2102", "2103", "2104", "2105", "2106", "2107", "2108",
    "2109", "2110", "2111", "2112", "2113", "2114", "2115", "2116",
    "2117", "2118", "2119", "2120", "2122", "2123", "2124", "2125",
    "2403", "2404", "2405",
}

# ─── ALÍQUOTAS INTERNAS POR UF ───────────────────────────────────────────────

ALIQUOTAS_INTERNAS_UF = {
    "AC": Decimal("17.00"), "AL": Decimal("19.00"), "AM": Decimal("20.00"),
    "AP": Decimal("18.00"), "BA": Decimal("20.50"), "CE": Decimal("18.00"),
    "DF": Decimal("20.00"), "ES": Decimal("17.00"), "GO": Decimal("17.00"),
    "MA": Decimal("22.00"), "MG": Decimal("18.00"), "MS": Decimal("17.00"),
    "MT": Decimal("17.00"), "PA": Decimal("19.00"), "PB": Decimal("18.00"),
    "PE": Decimal("20.50"), "PI": Decimal("21.00"), "PR": Decimal("19.50"),
    "RJ": Decimal("20.00"), "RN": Decimal("20.00"), "RO": Decimal("17.50"),
    "RR": Decimal("20.00"), "RS": Decimal("17.00"), "SC": Decimal("17.00"),
    "SE": Decimal("19.00"), "SP": Decimal("18.00"), "TO": Decimal("20.00"),
}

METODO_DIFAL = "FORA"

# ─── FUNÇÕES DE EXTRAÇÃO DE PDF ───────────────────────────────────────────────

def extrair_aliquota_do_pdf(arquivo_pdf):
    """Lê o PDF do Extrato do Simples Nacional e calcula a alíquota efetiva."""
    try:
        texto_completo = ""
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                texto_extraido = page.extract_text()
                if texto_extraido:
                    texto_completo += texto_extraido + "\n"

        receita_match = re.search(r"Receita Bruta Informada R\$\s*([\d\.]+,\d{2})", texto_completo)
        imposto_match = re.search(r"Principal\s+[\d\.]+,\d{2}.*?Total\s+([\d\.]+,\d{2})", texto_completo, re.DOTALL)
        
        if receita_match and imposto_match:
            receita_str = receita_match.group(1).replace(".", "").replace(",", ".")
            imposto_str = imposto_match.group(1).replace(".", "").replace(",", ".")
            
            receita = Decimal(receita_str)
            imposto = Decimal(imposto_str)
            
            if receita > 0:
                aliquota = (imposto / receita) * Decimal("100")
                return aliquota.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                
        return None
    except Exception as e:
        logging.error(f"Erro ao ler o PDF do Simples: {e}")
        return None

# ─── FUNÇÕES AUXILIARES ───────────────────────────────────────────────────────

def decimal_seguro(valor_str):
    if valor_str is None:
        return Decimal("0.00")
    valor_limpo = valor_str.strip().replace(",", ".")
    try:
        return Decimal(valor_limpo).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")

def encontrar_texto(elemento, caminho_com_ns):
    try:
        encontrado = elemento.find(caminho_com_ns)
        if encontrado is not None and encontrado.text:
            return encontrado.text.strip()
    except Exception:
        pass
    return None

def calcular_difal(valor_base, aliq_interestadual, aliq_interna_uf, metodo="FORA"):
    aliq_inter = aliq_interestadual / Decimal("100")
    aliq_int = aliq_interna_uf / Decimal("100")

    if metodo == "FORA":
        icms_destino = (valor_base * aliq_int).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        icms_origem = (valor_base * aliq_inter).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difal = icms_destino - icms_origem
    elif metodo == "DENTRO":
        base_dentro = (valor_base / (Decimal("1") - aliq_int)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        icms_destino = (base_dentro * aliq_int).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        icms_origem = (valor_base * aliq_inter).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        difal = icms_destino - icms_origem
    else:
        difal = Decimal("0.00")

    return max(difal, Decimal("0.00"))

# ─── PROCESSAMENTO DE XML ─────────────────────────────────────────────────────

def processar_xml_nfe(root, ns, caminho_arquivo, uf_destino_empresa):
    registros = []
    try:
        inf_nfe = root.find(f".//{ns}infNFe")
        if inf_nfe is None:
            inf_nfe = root

        ide = inf_nfe.find(f"{ns}ide")
        if ide is None:
            raise ValueError("Tag <ide> não encontrada no XML.")

        numero_nf = encontrar_texto(ide, f"{ns}nNF") or ""
        serie = encontrar_texto(ide, f"{ns}serie") or ""
        data_emissao = encontrar_texto(ide, f"{ns}dhEmi") or encontrar_texto(ide, f"{ns}dEmi") or ""
        tipo_operacao = encontrar_texto(ide, f"{ns}tpNF") or "" 
        modelo_doc = encontrar_texto(ide, f"{ns}mod") or "55"
        chave_nfe = encontrar_texto(inf_nfe, f"{ns}Id") or ""
        if chave_nfe.startswith("NFe"):
            chave_nfe = chave_nfe[3:]

        emit = inf_nfe.find(f"{ns}emit")
        cnpj_emit = encontrar_texto(emit, f"{ns}CNPJ") or encontrar_texto(emit, f"{ns}CPF") or "" if emit is not None else ""
        uf_emit = encontrar_texto(emit, f"{ns}enderEmit/{ns}UF") or "" if emit is not None else ""
        nome_emit = encontrar_texto(emit, f"{ns}xNome") or "" if emit is not None else ""

        dest = inf_nfe.find(f"{ns}dest")
        cnpj_dest = encontrar_texto(dest, f"{ns}CNPJ") or encontrar_texto(dest, f"{ns}CPF") or "" if dest is not None else ""
        uf_dest = encontrar_texto(dest, f"{ns}enderDest/{ns}UF") or "" if dest is not None else ""
        nome_dest = encontrar_texto(dest, f"{ns}xNome") or "" if dest is not None else ""

        operacao_interestadual = (uf_emit.upper() != uf_dest.upper()) and uf_emit and uf_dest

        for det in inf_nfe.findall(f"{ns}det"):
            prod = det.find(f"{ns}prod")
            if prod is None:
                continue

            cfop = encontrar_texto(prod, f"{ns}CFOP") or ""
            v_prod = decimal_seguro(encontrar_texto(prod, f"{ns}vProd"))
            v_desc = decimal_seguro(encontrar_texto(prod, f"{ns}vDesc"))
            v_item_liq = v_prod - v_desc
            codigo_produto = encontrar_texto(prod, f"{ns}cProd") or ""
            descricao_produto = encontrar_texto(prod, f"{ns}xProd") or ""

            imposto = det.find(f"{ns}imposto")
            csosn = ""
            cst_icms = ""
            p_icms = Decimal("0.00")
            v_icms_item = Decimal("0.00")

            if imposto is not None:
                icms_group = imposto.find(f"{ns}ICMS")
                if icms_group is not None:
                    for filho in icms_group:
                        csosn_tag = filho.find(f"{ns}CSOSN")
                        cst_tag = filho.find(f"{ns}CST")
                        picms_tag = filho.find(f"{ns}pICMS")
                        vicms_tag = filho.find(f"{ns}vICMS")
                        if csosn_tag is not None and csosn_tag.text:
                            csosn = csosn_tag.text.strip()
                        if cst_tag is not None and cst_tag.text:
                            cst_icms = cst_tag.text.strip()
                        if picms_tag is not None and picms_tag.text:
                            p_icms = decimal_seguro(picms_tag.text)
                        if vicms_tag is not None and vicms_tag.text:
                            v_icms_item = decimal_seguro(vicms_tag.text)

            cfop_limpo = cfop.replace(".", "").strip()
            cfop_4dig = cfop_limpo.zfill(4)

            categoria = "NAO_IDENTIFICADO"
            valor_receita_bruta = Decimal("0.00")
            valor_devolucao = Decimal("0.00")
            valor_entrada_interestadual = Decimal("0.00")
            difal_calculado = Decimal("0.00")
            tipo_difal = ""

            if tipo_operacao == "1":
                if cfop_4dig in CFOPS_RECEITA_BRUTA:
                    categoria = "SAIDA_RECEITA"
                    valor_receita_bruta = v_item_liq
                elif cfop_4dig in CFOPS_DEVOLUCAO_SAIDA:
                    categoria = "SAIDA_DEVOLUCAO_COMPRA"
                elif cfop_4dig in CFOPS_SAIDA_NAO_RECEITA:
                    categoria = "SAIDA_NAO_RECEITA"
                else:
                    categoria = "SAIDA_OUTROS"

            elif tipo_operacao == "0":
                if cfop_4dig in CFOPS_DEVOLUCAO_ENTRADA:
                    categoria = "ENTRADA_DEVOLUCAO_VENDA"
                    valor_devolucao = v_item_liq

                elif operacao_interestadual:
                    if cfop_4dig in CFOPS_ENTRADA_USO_CONSUMO_ATIVO:
                        categoria = "ENTRADA_DIFAL_USO_CONSUMO_ATIVO"
                        valor_entrada_interestadual = v_item_liq
                        aliq_interna = ALIQUOTAS_INTERNAS_UF.get(uf_destino_empresa.upper(),
                                        ALIQUOTAS_INTERNAS_UF.get(uf_dest.upper(), Decimal("18.00")))
                        difal_calculado = calcular_difal(v_item_liq, p_icms, aliq_interna, METODO_DIFAL)
                        tipo_difal = "DIFAL_USO_CONSUMO"

                    elif cfop_4dig in CFOPS_ENTRADA_COMERCIALIZACAO:
                        categoria = "ENTRADA_ANTECIPACAO_COMERCIALIZACAO"
                        valor_entrada_interestadual = v_item_liq
                        aliq_interna = ALIQUOTAS_INTERNAS_UF.get(uf_destino_empresa.upper(),
                                        ALIQUOTAS_INTERNAS_UF.get(uf_dest.upper(), Decimal("18.00")))
                        difal_calculado = calcular_difal(v_item_liq, p_icms, aliq_interna, METODO_DIFAL)
                        tipo_difal = "ANTECIPACAO_REVENDA"

                    else:
                        categoria = "ENTRADA_INTERESTADUAL_OUTROS"
                        valor_entrada_interestadual = v_item_liq
                else:
                    categoria = "ENTRADA_INTERNA"

            registro = {
                "arquivo": caminho_arquivo,
                "modelo": modelo_doc,
                "chave_nfe": chave_nfe,
                "numero_nf": numero_nf,
                "serie": serie,
                "data_emissao": data_emissao[:10] if len(data_emissao) >= 10 else data_emissao,
                "tipo_operacao": "SAIDA" if tipo_operacao == "1" else "ENTRADA",
                "cnpj_emitente": cnpj_emit,
                "nome_emitente": nome_emit,
                "uf_emitente": uf_emit,
                "cnpj_destinatario": cnpj_dest,
                "nome_destinatario": nome_dest,
                "uf_destinatario": uf_dest,
                "operacao_interestadual": "SIM" if operacao_interestadual else "NAO",
                "cfop": cfop,
                "codigo_produto": codigo_produto,
                "descricao_produto": descricao_produto,
                "csosn": csosn,
                "cst_icms": cst_icms,
                "v_prod": str(v_prod),
                "v_desc": str(v_desc),
                "v_item_liquido": str(v_item_liq),
                "p_icms": str(p_icms),
                "v_icms_item": str(v_icms_item),
                "categoria_fiscal": categoria,
                "valor_receita_bruta": str(valor_receita_bruta),
                "valor_devolucao_venda": str(valor_devolucao),
                "valor_entrada_interestadual": str(valor_entrada_interestadual),
                "difal_calculado": str(difal_calculado),
                "tipo_difal": tipo_difal,
                "metodo_difal": METODO_DIFAL if difal_calculado > Decimal("0.00") else "",
            }
            registros.append(registro)

    except Exception as e:
        logging.error(f"Erro ao processar NF-e | Arquivo: {caminho_arquivo} | Erro: {e}")

    return registros

def processar_xml_cte(root, ns, caminho_arquivo, uf_destino_empresa):
    registros = []
    try:
        inf_cte = root.find(f".//{ns}infCte")
        if inf_cte is None:
            inf_cte = root

        ide = inf_cte.find(f"{ns}ide")
        if ide is None:
            raise ValueError("Tag <ide> não encontrada no CT-e.")

        numero_cte = encontrar_texto(ide, f"{ns}nCT") or ""
        serie = encontrar_texto(ide, f"{ns}serie") or ""
        data_emissao = encontrar_texto(ide, f"{ns}dhEmi") or ""
        cfop = encontrar_texto(ide, f"{ns}CFOP") or ""
        modelo_doc = "57"
        chave_cte = encontrar_texto(inf_cte, f"{ns}Id") or ""
        if chave_cte.startswith("CTe"):
            chave_cte = chave_cte[3:]

        emit = inf_cte.find(f"{ns}emit")
        cnpj_emit = encontrar_texto(emit, f"{ns}CNPJ") or "" if emit is not None else ""
        nome_emit = encontrar_texto(emit, f"{ns}xNome") or "" if emit is not None else ""

        dest = inf_cte.find(f"{ns}dest")
        cnpj_dest = encontrar_texto(dest, f"{ns}CNPJ") or "" if dest is not None else ""
        nome_dest = encontrar_texto(dest, f"{ns}xNome") or "" if dest is not None else ""

        v_prest = inf_cte.find(f"{ns}vPrest")
        v_tprest = Decimal("0.00")
        if v_prest is not None:
            v_tprest_str = encontrar_texto(v_prest, f"{ns}vTPrest")
            v_tprest = decimal_seguro(v_tprest_str)

        ide_uf_ini = encontrar_texto(ide, f"{ns}UFIni") or ""
        ide_uf_fim = encontrar_texto(ide, f"{ns}UFFim") or ""

        operacao_interestadual = (ide_uf_ini.upper() != ide_uf_fim.upper()) and ide_uf_ini and ide_uf_fim

        cfop_limpo = cfop.replace(".", "").strip()
        cfop_4dig = cfop_limpo.zfill(4)

        categoria = "SAIDA_RECEITA" if cfop_4dig[0] in ("5", "6", "7") else "OUTROS_CTE"
        valor_receita_bruta = v_tprest if categoria == "SAIDA_RECEITA" else Decimal("0.00")

        registro = {
            "arquivo": caminho_arquivo,
            "modelo": modelo_doc,
            "chave_nfe": chave_cte,
            "numero_nf": numero_cte,
            "serie": serie,
            "data_emissao": data_emissao[:10] if len(data_emissao) >= 10 else data_emissao,
            "tipo_operacao": "SAIDA" if cfop_4dig[0] in ("5", "6", "7") else "ENTRADA",
            "cnpj_emitente": cnpj_emit,
            "nome_emitente": nome_emit,
            "uf_emitente": ide_uf_ini,
            "cnpj_destinatario": cnpj_dest,
            "nome_destinatario": nome_dest,
            "uf_destinatario": ide_uf_fim,
            "operacao_interestadual": "SIM" if operacao_interestadual else "NAO",
            "cfop": cfop,
            "codigo_produto": "",
            "descricao_produto": "PRESTACAO DE SERVICO DE TRANSPORTE",
            "csosn": "",
            "cst_icms": "",
            "v_prod": str(v_tprest),
            "v_desc": "0.00",
            "v_item_liquido": str(v_tprest),
            "p_icms": "0.00",
            "v_icms_item": "0.00",
            "categoria_fiscal": categoria,
            "valor_receita_bruta": str(valor_receita_bruta),
            "valor_devolucao_venda": "0.00",
            "valor_entrada_interestadual": "0.00",
            "difal_calculado": "0.00",
            "tipo_difal": "",
            "metodo_difal": "",
        }
        registros.append(registro)

    except Exception as e:
        logging.error(f"Erro ao processar CT-e | Arquivo: {caminho_arquivo} | Erro: {e}")

    return registros

def processar_xml_bytes(conteudo_bytes, caminho_referencia, uf_destino_empresa):
    registros = []
    try:
        conteudo_bytes = conteudo_bytes.lstrip()
        if conteudo_bytes.startswith(b"\xef\xbb\xbf"):
            conteudo_bytes = conteudo_bytes[3:]

        try:
            root = ET.fromstring(conteudo_bytes)
        except ET.ParseError as e:
            logging.error(f"XML mal formado | {caminho_referencia} | {e}")
            return registros

        root_tag = root.tag.lower()

        if "nfe" in root_tag or "nfeproc" in root_tag or "nfenfe" in root_tag:
            ns = NS_NFE
            registros = processar_xml_nfe(root, ns, caminho_referencia, uf_destino_empresa)

        elif "cte" in root_tag or "cteproc" in root_tag:
            ns = NS_CTE
            registros = processar_xml_cte(root, ns, caminho_referencia, uf_destino_empresa)

        elif "nfinf" in root_tag or "nfcenfe" in root_tag:
            ns = NS_NFE
            registros = processar_xml_nfe(root, ns, caminho_referencia, uf_destino_empresa)

        else:
            if NS_NFE in root.tag:
                registros = processar_xml_nfe(root, NS_NFE, caminho_referencia, uf_destino_empresa)
            elif NS_CTE in root.tag:
                registros = processar_xml_cte(root, NS_CTE, caminho_referencia, uf_destino_empresa)
            else:
                logging.error(f"Namespace não reconhecido | {caminho_referencia} | tag: {root.tag}")

    except Exception as e:
        logging.error(f"Erro inesperado ao processar XML | {caminho_referencia} | {e}")

    return registros

# ─── MÓDULO CEIFADOR: VARREDURA RECURSIVA DE ARQUIVOS (Adaptado para Memória) ─

def extrair_xmls_de_zip(zip_bytes, caminho_zip, uf_destino_empresa, profundidade=0):
    registros = []
    if profundidade > 10:
        logging.error(f"Limite de profundidade de ZIP atingido (10 níveis) | {caminho_zip}")
        return registros

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for nome_membro in zf.namelist():
                try:
                    caminho_membro = f"{caminho_zip}/{nome_membro}"
                    conteudo = zf.read(nome_membro)

                    if nome_membro.lower().endswith(".zip"):
                        registros_zip = extrair_xmls_de_zip(
                            conteudo, caminho_membro, uf_destino_empresa, profundidade + 1
                        )
                        registros.extend(registros_zip)

                    elif nome_membro.lower().endswith(".xml"):
                        registros_xml = processar_xml_bytes(conteudo, caminho_membro, uf_destino_empresa)
                        registros.extend(registros_xml)

                except zipfile.BadZipFile:
                    logging.error(f"ZIP interno corrompido | {caminho_zip}/{nome_membro}")
                except Exception as e:
                    logging.error(f"Erro ao extrair membro do ZIP | {caminho_zip}/{nome_membro} | {e}")

    except zipfile.BadZipFile:
        logging.error(f"Arquivo ZIP corrompido ou inválido | {caminho_zip}")
    except Exception as e:
        logging.error(f"Erro inesperado ao abrir ZIP | {caminho_zip} | {e}")

    return registros

def processar_uploads_streamlit(uploaded_files, uf_destino_empresa):
    todos_registros = []
    total_erros = 0

    for file in uploaded_files:
        nome_arquivo = file.name
        nome_lower = nome_arquivo.lower()
        conteudo = file.read()

        try:
            if nome_lower.endswith(".xml"):
                registros = processar_xml_bytes(conteudo, nome_arquivo, uf_destino_empresa)
                todos_registros.extend(registros)

            elif nome_lower.endswith(".zip"):
                registros = extrair_xmls_de_zip(conteudo, nome_arquivo, uf_destino_empresa)
                todos_registros.extend(registros)

        except Exception as e:
            logging.error(f"Erro ao acessar arquivo | {nome_arquivo} | {e}")
            total_erros += 1

    return todos_registros, total_erros

# ─── CONSOLIDAÇÃO E RELATÓRIO ─────────────────────────────────────────────────

def consolidar_apuracao(todos_registros, uf_destino_empresa, aliquota_simples_informada):
    receita_bruta_total = Decimal("0.00")
    devoluções_total = Decimal("0.00")
    entradas_interestaduais_total = Decimal("0.00")
    difal_uso_consumo_total = Decimal("0.00")
    antecipacao_revenda_total = Decimal("0.00")

    notas_sem_categoria = 0

    for reg in todos_registros:
        try:
            receita_bruta_total += Decimal(reg["valor_receita_bruta"])
            devoluções_total += Decimal(reg["valor_devolucao_venda"])
            entradas_interestaduais_total += Decimal(reg["valor_entrada_interestadual"])
            difal_calculado = Decimal(reg["difal_calculado"])
            tipo_difal = reg.get("tipo_difal", "")

            if tipo_difal == "DIFAL_USO_CONSUMO":
                difal_uso_consumo_total += difal_calculado
            elif tipo_difal == "ANTECIPACAO_REVENDA":
                antecipacao_revenda_total += difal_calculado

            if reg["categoria_fiscal"] == "NAO_IDENTIFICADO":
                notas_sem_categoria += 1

        except (InvalidOperation, KeyError):
            pass

    base_calculo_liquida = receita_bruta_total - devoluções_total
    if base_calculo_liquida < Decimal("0.00"):
        base_calculo_liquida = Decimal("0.00")

    aliquota_das = aliquota_simples_informada / Decimal("100")
    valor_estimado_das = (base_calculo_liquida * aliquota_das).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    difal_total = difal_uso_consumo_total + antecipacao_revenda_total
    total_geral_impostos = valor_estimado_das + difal_total

    return {
        "receita_bruta_total": receita_bruta_total,
        "devoluções_total": devoluções_total,
        "base_calculo_liquida": base_calculo_liquida,
        "aliquota_simples": aliquota_simples_informada,
        "valor_estimado_das": valor_estimado_das,
        "entradas_interestaduais_total": entradas_interestaduais_total,
        "difal_uso_consumo_total": difal_uso_consumo_total,
        "antecipacao_revenda_total": antecipacao_revenda_total,
        "difal_total": difal_total,
        "total_geral_impostos": total_geral_impostos,
        "total_registros": len(todos_registros),
        "notas_sem_categoria": notas_sem_categoria,
    }

def exportar_csv(todos_registros):
    if not todos_registros:
        return
    campos = list(todos_registros[0].keys())
    try:
        with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=campos, delimiter=";")
            writer.writeheader()
            writer.writerows(todos_registros)
    except Exception as e:
        logging.error(f"Erro ao exportar CSV | {e}")

# ─── INTERFACE STREAMLIT ──────────────────────────────────────────────────────

def main():
    st.title("🛡️ Sentinela - Apuração Simples Nacional")
    st.markdown("Módulo Web para processamento de arquivos XML fiscais, suportando *ZIPs Matrioskas* e geração do relatório detalhado para envio ao cliente.")
    
    with st.sidebar:
        st.header("Configurações Fiscais")
        uf_empresa = st.selectbox(
            "UF da Empresa", 
            options=list(ALIQUOTAS_INTERNAS_UF.keys()),
            index=list(ALIQUOTAS_INTERNAS_UF.keys()).index("SP")
        )
        
        st.markdown("---")
        st.markdown("**1. Extrato do Simples (PDF)**")
        pdf_extrato = st.file_uploader(
            "Upload do Extrato PGDAS para calcular alíquota", 
            type=["pdf"]
        )
        
        aliquota_simples = Decimal("0.00")
        if pdf_extrato:
            with st.spinner("Lendo Extrato..."):
                aliquota_calculada = extrair_aliquota_do_pdf(pdf_extrato)
                if aliquota_calculada:
                    st.success(f"Alíquota Efetiva detectada: {aliquota_calculada}%")
                    aliquota_simples = aliquota_calculada
                else:
                    st.error("Não foi possível localizar os valores no PDF. Insira manualmente abaixo.")
                    aliq_str = st.text_input("Alíquota Efetiva Manual (%)", value="0.00")
                    try:
                        aliquota_simples = Decimal(aliq_str.replace(",", "."))
                    except:
                        pass
        else:
            st.info("Aguardando PDF do Extrato para definir a alíquota.")
            aliq_str = st.text_input("Ou informe a Alíquota Efetiva Manual (%)", value="0.00")
            try:
                aliquota_simples = Decimal(aliq_str.replace(",", "."))
            except:
                pass

        st.markdown("---")
        st.markdown("**2. Arquivos Fiscais (XML/ZIP)**")
        st.markdown("- NF-e (55), CT-e (57), NFC-e (65/42)")

    st.subheader("Importação de Dados")
    arquivos_upados = st.file_uploader(
        "Arraste os arquivos XML ou ZIP contendo as notas", 
        accept_multiple_files=True, 
        type=["xml", "zip"]
    )

    if st.button("Executar Apuração") and arquivos_upados:
        if aliquota_simples <= Decimal("0.00"):
            st.error("Por favor, faça o upload do Extrato do PGDAS ou informe uma alíquota maior que zero na barra lateral antes de processar.")
            return

        with st.spinner("O Ceifador está processando os arquivos..."):
            open(LOG_FILE, 'w').close() 
            
            todos_registros, total_erros = processar_uploads_streamlit(arquivos_upados, uf_empresa)

            if not todos_registros:
                st.warning("Nenhum documento fiscal processado com sucesso. Verifique os arquivos.")
                return
            
            apuracao = consolidar_apuracao(todos_registros, uf_empresa, aliquota_simples)
            exportar_csv(todos_registros)

            def fmt(valor):
                return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

            st.success(f"Apuração concluída! {apuracao['total_registros']} itens processados (Erros ignorados: {total_erros}).")

            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Apuração do DAS (Saídas)")
                st.metric("Receita Bruta Total", fmt(apuracao['receita_bruta_total']))
                st.metric("(-) Devoluções de Vendas", fmt(apuracao['devoluções_total']))
                st.metric("Base de Cálculo Líquida", fmt(apuracao['base_calculo_liquida']))
                st.metric(f"Valor Estimado do DAS ({apuracao['aliquota_simples']}%)", fmt(apuracao['valor_estimado_das']))
            
            with col2:
                st.markdown("### Apuração de DIFAL / Antecipação (Entradas)")
                st.metric("Compras Interestaduais", fmt(apuracao['entradas_interestaduais_total']))
                st.metric("DIFAL Uso/Consumo", fmt(apuracao['difal_uso_consumo_total']))
                st.metric("Antecipação Tributária", fmt(apuracao['antecipacao_revenda_total']))
                st.metric("Total DIFAL + Antecipação", fmt(apuracao['difal_total']))

            st.markdown("---")
            st.markdown(f"### **TOTAL GERAL DE IMPOSTOS DO PERÍODO: {fmt(apuracao['total_geral_impostos'])}**")

            if apuracao['notas_sem_categoria'] > 0:
                st.warning(f"Atenção: {apuracao['notas_sem_categoria']} item(ns) com CFOP não classificado. Revise a planilha analítica.")

            col_btn1, col_btn2 = st.columns(2)
            
            if os.path.exists(CSV_FILE):
                with open(CSV_FILE, "rb") as file:
                    col_btn1.download_button(
                        label="📥 Baixar Planilha Analítica (CSV)",
                        data=file,
                        file_name=CSV_FILE,
                        mime="text/csv"
                    )
            
            if os.path.exists(LOG_FILE) and os.path.getsize(LOG_FILE) > 0:
                with open(LOG_FILE, "rb") as log_file:
                    col_btn2.download_button(
                        label="⚠️ Baixar Log de Erros",
                        data=log_file,
                        file_name=LOG_FILE,
                        mime="text/plain"
                    )

if __name__ == "__main__":
    main()
