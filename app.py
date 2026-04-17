"""
Apuração do Simples Nacional — ficheiro único para deploy (só `app.py` + `requirements.txt`).
"""
from __future__ import annotations
import json
import os
from collections import Counter, defaultdict
import zipfile
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, NamedTuple

import streamlit as st
import pandas as pd

# ── Motor: tabelas ──────────────────────────────────────────────────────────
class Faixa(NamedTuple):
    num: int
    lim_inf: Decimal
    lim_sup: Decimal
    aliq_nom: Decimal
    deducao: Decimal

def _d(s): return Decimal(str(s))

# ── Tabelas nominais ──────────────────────────────────────────────────────────
TABELAS: Dict[str, List[Faixa]] = {
    "I": [
        Faixa(1, _d("0"),          _d("180000"),  _d("0.04"),  _d("0")),
        Faixa(2, _d("180000.01"),  _d("360000"),  _d("0.073"), _d("5940")),
        Faixa(3, _d("360000.01"),  _d("720000"),  _d("0.095"), _d("13860")),
        Faixa(4, _d("720000.01"),  _d("1800000"), _d("0.107"), _d("22500")),
        Faixa(5, _d("1800000.01"),_d("3600000"),  _d("0.143"), _d("87300")),
        Faixa(6, _d("3600000.01"),_d("4800000"),  _d("0.19"),  _d("378000")),
    ],
    "II": [
        Faixa(1, _d("0"),          _d("180000"),  _d("0.045"), _d("0")),
        Faixa(2, _d("180000.01"),  _d("360000"),  _d("0.078"), _d("5940")),
        Faixa(3, _d("360000.01"),  _d("720000"),  _d("0.10"),  _d("13860")),
        Faixa(4, _d("720000.01"),  _d("1800000"), _d("0.112"), _d("22500")),
        Faixa(5, _d("1800000.01"),_d("3600000"),  _d("0.147"), _d("85500")),
        Faixa(6, _d("3600000.01"),_d("4800000"),  _d("0.30"),  _d("720000")),
    ],
    "III": [
        Faixa(1, _d("0"),          _d("180000"),  _d("0.06"),  _d("0")),
        Faixa(2, _d("180000.01"),  _d("360000"),  _d("0.112"), _d("9360")),
        Faixa(3, _d("360000.01"),  _d("720000"),  _d("0.135"), _d("17640")),
        Faixa(4, _d("720000.01"),  _d("1800000"), _d("0.16"),  _d("35640")),
        Faixa(5, _d("1800000.01"),_d("3600000"),  _d("0.21"),  _d("125640")),
        Faixa(6, _d("3600000.01"),_d("4800000"),  _d("0.33"),  _d("648000")),
    ],
    "IV": [
        Faixa(1, _d("0"),          _d("180000"),  _d("0.045"), _d("0")),
        Faixa(2, _d("180000.01"),  _d("360000"),  _d("0.09"),  _d("8100")),
        Faixa(3, _d("360000.01"),  _d("720000"),  _d("0.102"), _d("12420")),
        Faixa(4, _d("720000.01"),  _d("1800000"), _d("0.14"),  _d("39780")),
        Faixa(5, _d("1800000.01"),_d("3600000"),  _d("0.22"),  _d("183780")),
        Faixa(6, _d("3600000.01"),_d("4800000"),  _d("0.33"),  _d("828000")),
    ],
    "V": [
        Faixa(1, _d("0"),          _d("180000"),  _d("0.155"), _d("0")),
        Faixa(2, _d("180000.01"),  _d("360000"),  _d("0.18"),  _d("4500")),
        Faixa(3, _d("360000.01"),  _d("720000"),  _d("0.195"), _d("9900")),
        Faixa(4, _d("720000.01"),  _d("1800000"), _d("0.205"), _d("17100")),
        Faixa(5, _d("1800000.01"),_d("3600000"),  _d("0.23"),  _d("62100")),
        Faixa(6, _d("3600000.01"),_d("4800000"),  _d("0.305"), _d("540000")),
    ],
}

# ── Partilha por tributo (% sobre o DAS total) ────────────────────────────────
PARTILHAS: Dict[str, Dict[int, Dict[str, Decimal]]] = {
    "I": {
        1: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1274"),"PIS":_d("0.0276"),"CPP":_d("0.415"), "ICMS":_d("0.34")},
        2: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1274"),"PIS":_d("0.0276"),"CPP":_d("0.415"), "ICMS":_d("0.34")},
        3: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1274"),"PIS":_d("0.0276"),"CPP":_d("0.42"),  "ICMS":_d("0.335")},
        4: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1274"),"PIS":_d("0.0276"),"CPP":_d("0.42"),  "ICMS":_d("0.335")},
        5: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1274"),"PIS":_d("0.0276"),"CPP":_d("0.42"),  "ICMS":_d("0.335")},
        6: {"IRPJ":_d("0.135"),"CSLL":_d("0.10"), "COFINS":_d("0.2827"),"PIS":_d("0.0613"),"CPP":_d("0.421"),"ICMS":_d("0")},
    },
    "II": {
        1: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1151"),"PIS":_d("0.0249"),"CPP":_d("0.375"),"IPI":_d("0.075"),"ICMS":_d("0.32")},
        2: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1151"),"PIS":_d("0.0249"),"CPP":_d("0.375"),"IPI":_d("0.075"),"ICMS":_d("0.32")},
        3: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1151"),"PIS":_d("0.0249"),"CPP":_d("0.375"),"IPI":_d("0.075"),"ICMS":_d("0.32")},
        4: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1151"),"PIS":_d("0.0249"),"CPP":_d("0.375"),"IPI":_d("0.075"),"ICMS":_d("0.32")},
        5: {"IRPJ":_d("0.055"),"CSLL":_d("0.035"),"COFINS":_d("0.1151"),"PIS":_d("0.0249"),"CPP":_d("0.375"),"IPI":_d("0.075"),"ICMS":_d("0.32")},
        6: {"IRPJ":_d("0.085"),"CSLL":_d("0.075"),"COFINS":_d("0.2096"),"PIS":_d("0.0454"),"CPP":_d("0.235"),"IPI":_d("0.35"), "ICMS":_d("0")},
    },
    "III": {
        1: {"IRPJ":_d("0.04"),"CSLL":_d("0.035"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0.434"),"ISS":_d("0.32")},
        2: {"IRPJ":_d("0.04"),"CSLL":_d("0.035"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0.434"),"ISS":_d("0.32")},
        3: {"IRPJ":_d("0.04"),"CSLL":_d("0.035"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0.434"),"ISS":_d("0.325")},
        4: {"IRPJ":_d("0.04"),"CSLL":_d("0.035"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0.434"),"ISS":_d("0.325")},
        5: {"IRPJ":_d("0.04"),"CSLL":_d("0.035"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0.434"),"ISS":_d("0.335")},
        6: {"IRPJ":_d("0.35"), "CSLL":_d("0.15"),"COFINS":_d("0.1405"),"PIS":_d("0.0305"),"CPP":_d("0"),    "ISS":_d("0.335")},
    },
    "IV": {
        1: {"IRPJ":_d("0.18"), "CSLL":_d("0.15"),"COFINS":_d("0.425"), "PIS":_d("0.0925"),"ISS":_d("0.1525")},
        2: {"IRPJ":_d("0.18"), "CSLL":_d("0.15"),"COFINS":_d("0.425"), "PIS":_d("0.0925"),"ISS":_d("0.1525")},
        3: {"IRPJ":_d("0.185"),"CSLL":_d("0.15"),"COFINS":_d("0.4375"),"PIS":_d("0.095"), "ISS":_d("0.1325")},
        4: {"IRPJ":_d("0.185"),"CSLL":_d("0.15"),"COFINS":_d("0.4375"),"PIS":_d("0.095"), "ISS":_d("0.1325")},
        5: {"IRPJ":_d("0.185"),"CSLL":_d("0.15"),"COFINS":_d("0.4375"),"PIS":_d("0.095"), "ISS":_d("0.1325")},
        6: {"IRPJ":_d("0.35"), "CSLL":_d("0.15"),"COFINS":_d("0.4375"),"PIS":_d("0.095"), "ISS":_d("0")},
    },
    "V": {
        1: {"IRPJ":_d("0.25"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0.28"), "ISS":_d("0.14")},
        2: {"IRPJ":_d("0.23"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0.28"), "ISS":_d("0.17")},
        3: {"IRPJ":_d("0.24"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0.28"), "ISS":_d("0.18")},
        4: {"IRPJ":_d("0.21"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0.28"), "ISS":_d("0.21")},
        5: {"IRPJ":_d("0.23"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0.28"), "ISS":_d("0.23")},
        6: {"IRPJ":_d("0.35"),"CSLL":_d("0.15"),"COFINS":_d("0.1425"),"PIS":_d("0.0309"),"CPP":_d("0"),    "ISS":_d("0.335")},
    },
}

# CFOPs de saída que compõem receita bruta
CFOPS_RECEITA_BRUTA = {
    "5101","6101","5102","6102","5103","6103","5104","6104",
    "5105","6105","5106","6106","5109","6109","5110","6110",
    "5111","6111","5112","6112","5113","6113","5114","6114",
    "5115","6115","5116","6116","5117","6117","5118","6118",
    "5119","6119","5120","6120","5122","6122","5123","6123",
    "5124","6124","5125","6125","5126","6126","5127","6127",
    "5128","6128","5401","6401","5402","6402","5403","6403",
    "5404","6404","5405","6405","5501","6501",
    "5933","6933","5949","6949",
}

# CFOPs de saída que NÃO são receita (transferência, imobilizado, bonificação)
CFOPS_NAO_RECEITA = {
    "5351","6351","5352","6352","5353","6353","5354","6354",
    "5355","6355","5356","6356","5357","6357","5358","6358",
    "5551","6551","5552","6552","5553","6553","5554","6554",
    "5555","6555","5556","6556","5557","6557","5910","5911",
    "5912","5913","5914","5915","5916","5917","5918","5919",
    "5920","5921","5922","5923","5924","5925",
}

# CFOPs de devolução (entrada que estorna venda anterior)
CFOPS_DEVOLUCAO = {
    "1201","2201","1202","2202","1203","2203","1204","2204",
    "1410","2410","1411","2411","1503","2503",
}

# CFOPs que indicam serviço dentro de NF-e
CFOPS_SERVICO = {
    "5933","6933","5124","6124","5125","6125",
}

# CST/CSOSN que indicam ST
CSOSN_ST = {"201","202","203","500","700","900"}
CST_ST   = {"10","30","60","70"}

LIMITE_SIMPLES = _d("4800000")
FATOR_R_MIN    = _d("0.28")
TRIBUTOS_ORDEM = ["IRPJ","CSLL","COFINS","PIS","CPP","IPI","ICMS","ISS"]

ANEXOS_DESC = {
    "I":   "Anexo I — Comércio",
    "II":  "Anexo II — Indústria",
    "III": "Anexo III — Serviços / Locação",
    "IV":  "Anexo IV — Serviços específicos (CPP fora do DAS)",
    "V":   "Anexo V — Serviços com Fator R",
}

def get_faixa(anexo: str, rbt12: Decimal) -> Faixa:
    for f in TABELAS[anexo]:
        if rbt12 <= f.lim_sup:
            return f
    return TABELAS[anexo][-1]

def get_partilha(anexo: str, num_faixa: int) -> Dict[str, Decimal]:
    return dict(PARTILHAS[anexo][num_faixa])

# ── Motor: leitor XML ───────────────────────────────────────────────────────
import zipfile, io, re
from xml.etree import ElementTree as ET

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_CTE = "http://www.portalfiscal.inf.br/cte"

# ── Estrutura de nota normalizada ─────────────────────────────────────────────
@dataclass
class ItemNota:
    cfop: str
    valor: Decimal
    tem_st: bool
    tipo: str  # "mercadoria" | "servico" | "frete"

@dataclass
class NotaFiscal:
    chave: str
    modelo: str           # "55","65","57","NFSe","CANC"
    cnpj_emitente: str
    cnpj_destinatario: str
    tipo_op: str          # "0"=entrada "1"=saída
    valor_total: Decimal
    itens: List[ItemNota]
    cancelada: bool = False
    is_devolucao: bool = False
    is_transferencia: bool = False
    is_frete_cte: bool = False
    alertas: List[str] = field(default_factory=list)
    # Explicação de cada decisão — para mostrar ao usuário
    decisoes: List[str] = field(default_factory=list)

    @property
    def valor_receita(self) -> Decimal:
        """Valor que entra na receita bruta (exclui frete CTE e transferências)."""
        if self.cancelada or self.is_frete_cte or self.is_transferencia:
            return Decimal("0")
        sinal = Decimal("-1") if self.is_devolucao else Decimal("1")
        return sinal * self.valor_total

    @property
    def tem_st(self) -> bool:
        return any(i.tem_st for i in self.itens)

    @property
    def cfops(self) -> List[str]:
        return [i.cfop for i in self.itens]

# ── Helpers ───────────────────────────────────────────────────────────────────
def _limpar(s: str) -> str:
    return re.sub(r"\D", "", str(s or ""))

def _dec(s) -> Decimal:
    try:
        return Decimal(str(s).strip())
    except:
        return Decimal("0")

def _t(root: ET.Element, *tags, ns: str = "") -> str:
    for tag in tags:
        path = f".//{{{ns}}}{tag}" if ns else f".//{tag}"
        el = root.find(path)
        if el is not None and el.text:
            return el.text.strip()
    return ""

# ── Parser NF-e / NFC-e ───────────────────────────────────────────────────────
def _parse_nfe(conteudo: bytes) -> Optional[NotaFiscal]:
    try:
        root = ET.fromstring(conteudo.decode("utf-8", errors="ignore").lstrip())
        ns   = NS_NFE
        inf  = root.find(f".//{{{ns}}}infNFe")
        if inf is None: return None

        ide    = inf.find(f"{{{ns}}}ide")
        modelo = _t(ide, "mod", ns=ns)
        if modelo not in ("55","65"): return None

        chave   = inf.attrib.get("Id","")[3:]
        tp_nf   = _t(ide, "tpNF", ns=ns)   # 0=entrada 1=saída
        emit    = _limpar(_t(inf, "emit/{%s}CNPJ" % ns) or _t(inf, "CNPJ", ns=ns))
        dest_el = inf.find(f"{{{ns}}}dest")
        dest    = ""
        if dest_el is not None:
            dest = _limpar(_t(dest_el,"CNPJ",ns=ns) or _t(dest_el,"CPF",ns=ns))

        v_total = _dec(_t(inf, "vNF", ns=ns) or _t(root,"vNF",ns=ns))
        decisoes: List[str] = []
        alertas:  List[str] = []
        itens:    List[ItemNota] = []

        is_dev = False
        is_transf = False

        for det in inf.findall(f"{{{ns}}}det"):
            prod = det.find(f"{{{ns}}}prod")
            if prod is None: continue
            cfop  = _t(prod,"CFOP",ns=ns).replace(".","")
            vProd = _dec(_t(prod,"vProd",ns=ns))

            # ST por item
            icms_node = det.find(f".//{{{ns}}}ICMS")
            item_st = False
            if icms_node is not None:
                csosn = _t(icms_node,"CSOSN",ns=ns)
                cst   = _t(icms_node,"CST",  ns=ns)
                if csosn in CSOSN_ST or cst in CST_ST:
                    item_st = True

            # Tipo do item
            if cfop in CFOPS_SERVICO:
                tipo = "servico"
            elif cfop in {"5352","6352","5351","6351","5353","6353"}:
                tipo = "transferencia"
                is_transf = True
            else:
                tipo = "mercadoria"

            # Devolução
            if cfop in CFOPS_DEVOLUCAO:
                is_dev = True

            itens.append(ItemNota(cfop=cfop, valor=vProd, tem_st=item_st, tipo=tipo))

        # Decisões explicadas
        if tp_nf == "0":
            decisoes.append("Nota de ENTRADA — não entra na receita bruta como venda.")
        if is_dev:
            decisoes.append("CFOP de devolução identificado — valor será SUBTRAÍDO da receita do mês.")
        if is_transf:
            decisoes.append("CFOP de transferência entre estabelecimentos — NÃO entra na receita bruta.")
        if any(i.tem_st for i in itens):
            decisoes.append("Itens com ST detectados (CSOSN 201/202/203/500) — parcela ICMS será removida da alíquota.")

        return NotaFiscal(
            chave=chave, modelo=modelo,
            cnpj_emitente=emit, cnpj_destinatario=dest,
            tipo_op=tp_nf, valor_total=v_total, itens=itens,
            is_devolucao=is_dev, is_transferencia=is_transf,
            decisoes=decisoes, alertas=alertas,
        )
    except Exception as e:
        return None

# ── Parser CT-e ───────────────────────────────────────────────────────────────
def _parse_cte(conteudo: bytes) -> Optional[NotaFiscal]:
    try:
        root = ET.fromstring(conteudo.decode("utf-8", errors="ignore").lstrip())
        ns   = NS_CTE
        inf  = root.find(f".//{{{ns}}}infCte")
        if inf is None: return None
        ide = inf.find(f"{{{ns}}}ide")
        if _t(ide,"mod",ns=ns) != "57": return None

        chave = inf.attrib.get("Id","")[3:]
        emit  = _limpar(_t(inf,"emit/{%s}CNPJ" % ns) or _t(inf,"CNPJ",ns=ns))
        v_tot = _dec(_t(root,"vTPrest",ns=ns) or _t(root,"vTotServ",ns=ns))
        tp_nf = _t(ide,"tpNF",ns=ns) or "1"

        return NotaFiscal(
            chave=chave, modelo="57",
            cnpj_emitente=emit, cnpj_destinatario="",
            tipo_op=tp_nf, valor_total=v_tot,
            itens=[ItemNota(cfop="CTE", valor=v_tot, tem_st=False, tipo="frete")],
            is_frete_cte=True,
            decisoes=["CT-e de frete — NÃO entra na receita bruta do Simples. "
                      "Se o frete já está embutido na NF-e, contar de novo seria duplicar."],
            alertas=["CT-e excluído da receita bruta automaticamente."],
        )
    except:
        return None

# ── Parser NFS-e (múltiplos namespaces municipais) ────────────────────────────
def _parse_nfse(conteudo: bytes) -> Optional[NotaFiscal]:
    try:
        xml_str = conteudo.decode("utf-8", errors="ignore").lstrip()
        root = ET.fromstring(xml_str)
    except:
        return None

    tag_raiz = root.tag.lower()
    # Procura nó de NFS-e em envelopes
    if not any(k in tag_raiz for k in ("nfse","compnfse","rps")):
        for child in root.iter():
            if any(k in child.tag.lower() for k in ("nfse","compnfse")):
                root = child; break
        else:
            return None

    m  = re.match(r"\{(.+?)\}", root.tag)
    ns = m.group(1) if m else ""

    def tx(*tags):
        for tag in tags:
            path = f".//{{{ns}}}{tag}" if ns else f".//{tag}"
            el = root.find(path)
            if el is not None and el.text:
                return el.text.strip()
        return ""

    num      = tx("Numero","NumeroNFe","NumNFSe","nNFSe") or "0"
    cnpj_e   = _limpar(tx("Cnpj","CNPJ","CnpjPrestador","cnpj"))
    v_serv   = _dec(tx("ValorServicos","ValorLiquido","ValorNfse","Valor","ValorNF","vNF","ValorBruto"))
    chave    = f"NFSE_{cnpj_e}_{num}"

    if v_serv == 0:
        return None

    return NotaFiscal(
        chave=chave, modelo="NFSe",
        cnpj_emitente=cnpj_e, cnpj_destinatario="",
        tipo_op="1", valor_total=v_serv,
        itens=[ItemNota(cfop="SERV", valor=v_serv, tem_st=False, tipo="servico")],
        decisoes=[f"NFS-e municipal (namespace: '{ns or 'sem namespace'}') — "
                   "serviço entra pelo Anexo III, IV ou V conforme atividade cadastrada."],
    )

# ── Parser de evento de cancelamento ─────────────────────────────────────────
def _parse_cancelamento(conteudo: bytes) -> List[str]:
    """Retorna lista de chaves canceladas encontradas no arquivo."""
    chaves = []
    try:
        root = ET.fromstring(conteudo.decode("utf-8", errors="ignore").lstrip())
        ns   = NS_NFE
        for ev in root.findall(f".//{{{ns}}}infEvento"):
            if _t(ev,"tpEvento",ns=ns) == "110111":
                ch = _t(ev,"chNFe",ns=ns)
                if ch: chaves.append(ch)
        # Também tenta chave direta na infNFe (arquivo de NF-e cancelada)
        inf = root.find(f".//{{{ns}}}infNFe")
        if inf is not None:
            ch = inf.attrib.get("Id","")[3:]
            if ch and _t(root,"dhCancelamento",ns=ns):
                chaves.append(ch)
    except:
        pass
    return chaves

# ── Detecção automática de tipo ───────────────────────────────────────────────
def _detectar(conteudo: bytes) -> tuple:
    """Retorna (tipo, resultado) onde tipo é 'nota'|'cancelamento'."""
    try:
        txt = conteudo.decode("utf-8", errors="ignore").lower()
    except:
        return ("ignorado", None)

    # Evento de cancelamento
    if "inevento" in txt and "110111" in txt:
        return ("cancelamento", _parse_cancelamento(conteudo))

    # CT-e
    if "infcte" in txt:
        r = _parse_cte(conteudo)
        if r: return ("nota", r)

    # NFS-e
    if any(k in txt[:800] for k in ("nfse","compnfse","numnfse")):
        r = _parse_nfse(conteudo)
        if r: return ("nota", r)

    # NF-e / NFC-e
    if "infnfe" in txt:
        r = _parse_nfe(conteudo)
        if r: return ("nota", r)

    return ("ignorado", None)

# ── Entrada principal ─────────────────────────────────────────────────────────
def ler_arquivos(arquivos: List[tuple]) -> List[NotaFiscal]:
    """
    Recebe lista de (nome, bytes). Suporta ZIPs aninhados.
    Aplica cancelamentos automaticamente.
    """
    notas:    List[NotaFiscal] = []
    canceladas: set            = set()
    _processar(arquivos, notas, canceladas)

    # Aplica cancelamentos
    for nota in notas:
        if nota.chave in canceladas and not nota.cancelada:
            nota.cancelada = True
            nota.decisoes.append("CANCELADA — evento de cancelamento encontrado nos arquivos enviados.")

    return notas

def _processar(arquivos: List[tuple], notas: List[NotaFiscal], canceladas: set):
    for nome, conteudo in arquivos:
        nl = nome.lower()
        if nl.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
                    internos = [(n, z.read(n)) for n in z.namelist()]
                _processar(internos, notas, canceladas)
            except:
                pass
        elif nl.endswith(".xml"):
            tipo, resultado = _detectar(conteudo)
            if tipo == "nota" and resultado:
                notas.append(resultado)
            elif tipo == "cancelamento" and resultado:
                canceladas.update(resultado)

# ── Motor: cálculo DAS ───────────────────────────────────────────────────────
getcontext().prec = 60
D2  = Decimal("0.01")
D13 = Decimal("0.0000000000001")

# ── Configuração da empresa (informada pelo usuário) ──────────────────────────
@dataclass
class ConfigEmpresa:
    cnpj_raiz: str           # 8 primeiros dígitos — identifica o cliente na apuração
    rbt12: Decimal
    # Lista de segmentos: cada um tem anexo, tipo e flags especiais
    segmentos: List[dict]
    nome: str = ""           # opcional (apelido); tela usa CNPJ raiz se vazio
    folha12: Optional[Decimal] = None     # para Fator R
    receita_servico_manual: Optional[Decimal] = None  # NFS-e sem XML / valores informados à mão
    # Flags de desenquadramento
    icms_fora_simples: bool = False
    iss_fora_simples: bool  = False


def rotulo_empresa(cfg: ConfigEmpresa) -> str:
    """Nome amigável na tabela: apelido opcional ou CNPJ raiz formatado."""
    n = (cfg.nome or "").strip()
    if n:
        return n
    r = cfg.cnpj_raiz
    if len(r) == 8 and r.isdigit():
        return f"Raiz {r[:2]}.{r[2:5]}.{r[5:8]}"
    return f"Raiz {r}"


def segmentos_perfil_rapido(perfil_id: str, st_comercio: bool) -> List[dict]:
    """Monta `segmentos` a partir do perfil escolhido no formulário rápido."""
    if perfil_id == "com_i":
        return [{"tipo": "mercadoria", "anexo": "I", "tem_st": st_comercio}]
    if perfil_id == "srv_iii":
        return [{"tipo": "servico", "anexo": "III", "tem_st": False}]
    if perfil_id == "srv_iv":
        return [{"tipo": "servico", "anexo": "IV", "tem_st": False}]
    if perfil_id == "srv_v":
        return [{"tipo": "servico", "anexo": "V", "tem_st": False}]
    if perfil_id == "mix_i_iii":
        return [
            {"tipo": "mercadoria", "anexo": "I", "tem_st": st_comercio},
            {"tipo": "servico", "anexo": "III", "tem_st": False},
        ]
    return []


OPTS_PERFIL_RAPIDO: List[Tuple[str, str]] = [
    ("com_i", "Só comércio / revenda — Anexo I"),
    ("srv_iii", "Só serviços — Anexo III"),
    ("srv_iv", "Só serviços — Anexo IV"),
    ("srv_v", "Só serviços — Anexo V"),
    ("mix_i_iii", "Comércio (I) + serviços (III) no mesmo CNPJ"),
    ("adv", "Personalizado (vários segmentos à mão)"),
]


# ── Resultado ─────────────────────────────────────────────────────────────────
@dataclass
class SegApurado:
    tipo: str
    anexo: str
    anexo_efetivo: str         # pode mudar pelo Fator R
    tem_st: bool
    receita: Decimal
    faixa: int
    aliq_nominal: Decimal
    deducao: Decimal
    aliq_efetiva: Decimal      # 13 casas — igual ao PGDAS
    das: Decimal
    partilha: Dict[str, Decimal]
    passos: List[str]          # explicações passo a passo do cálculo


@dataclass
class EstabelecimentoResumo:
    """Um CNPJ completo (matriz ou filial) com receita somada nos XMLs deste cliente."""
    cnpj14: str  # 14 dígitos; vazio se linha só de serviço manual
    papel: str
    receita: Decimal
    notas: int


@dataclass
class ResultadoEmpresa:
    nome: str
    cnpj_raiz: str
    rbt12: Decimal
    fator_r: Optional[Decimal]
    receita_total: Decimal
    das_total: Decimal
    segmentos: List[SegApurado]
    notas_validas: int
    notas_canceladas: int
    notas_devolucao: int
    notas_frete: int
    notas_transferencia: int
    alertas: List[str]
    estabelecimentos: List[EstabelecimentoResumo] = field(default_factory=list)

# ── Cálculo core ──────────────────────────────────────────────────────────────

def _aliq_efetiva(rbt12: Decimal, aliq_nom: Decimal, ded: Decimal) -> Decimal:
    """Fórmula PGDAS: (RBT12 × Aliq − PD) / RBT12 com 13 casas decimais."""
    return ((rbt12 * aliq_nom - ded) / rbt12).quantize(D13, ROUND_HALF_UP)

def _remover_tributo(partilha: Dict[str, Decimal], tributo: str, passos: List[str]) -> Dict[str, Decimal]:
    """Remove um tributo da partilha e redistribui proporcionalmente entre os demais."""
    pct = partilha.get(tributo, Decimal("0"))
    if pct == 0:
        return partilha
    sem = {k: v for k, v in partilha.items() if k != tributo}
    total_sem = sum(sem.values())
    nova = {tributo: Decimal("0")}
    for t, p in sem.items():
        nova[t] = (p / total_sem).quantize(D13) if total_sem > 0 else Decimal("0")
    passos.append(
        f"  → {tributo} removido da partilha ({float(pct):.2%}). "
        f"Os demais tributos foram redistribuídos proporcionalmente."
    )
    return nova

def _calcular_segmento(
    receita: Decimal,
    rbt12: Decimal,
    anexo: str,
    tem_st: bool,
    icms_fora: bool,
    iss_fora: bool,
    folha12: Optional[Decimal],
) -> SegApurado:
    passos: List[str] = []
    alertas_seg: List[str] = []

    # ── Fator R ──────────────────────────────────────────────────────────────
    anexo_efetivo = anexo
    fator_r = None
    if anexo == "V":
        if folha12 is None or folha12 == 0:
            passos.append(
                "Anexo V sem folha informada — Fator R não calculado. "
                "Tributando pelo Anexo V. ATENÇÃO: informe a folha de pagamento dos 12 meses "
                "(salários brutos + pró-labore + encargos patronais + FGTS)."
            )
        else:
            fator_r = (folha12 / rbt12).quantize(Decimal("0.0001"), ROUND_HALF_UP)
            if fator_r >= FATOR_R_MIN:
                anexo_efetivo = "III"
                passos.append(
                    f"Fator R = {float(fator_r):.2%} ≥ 28% → ANEXO III aplicado (menor alíquota). "
                    f"A empresa tem folha robusta em relação ao faturamento."
                )
            else:
                passos.append(
                    f"Fator R = {float(fator_r):.2%} < 28% → ANEXO V aplicado (maior alíquota). "
                    f"Se isso parece errado, verifique se o pró-labore e encargos foram incluídos na folha."
                )

    # ── Faixa e alíquota nominal ──────────────────────────────────────────────
    faixa = get_faixa(anexo_efetivo, rbt12)
    passos.append(
        f"RBT12 = R$ {float(rbt12):,.2f} → Faixa {faixa.num} do {ANEXOS_DESC[anexo_efetivo]}. "
        f"Alíquota nominal: {float(faixa.aliq_nom):.2%} | Dedução: R$ {float(faixa.deducao):,.2f}"
    )

    # ── Alíquota efetiva ──────────────────────────────────────────────────────
    ae = _aliq_efetiva(rbt12, faixa.aliq_nom, faixa.deducao)
    passos.append(
        f"Alíquota efetiva = ({float(rbt12):,.2f} × {float(faixa.aliq_nom):.4%} − {float(faixa.deducao):,.2f}) "
        f"÷ {float(rbt12):,.2f} = {float(ae):.13%}"
    )

    # ── Partilha base ─────────────────────────────────────────────────────────
    partilha = get_partilha(anexo_efetivo, faixa.num)

    # ── ST (Substituição Tributária) ──────────────────────────────────────────
    if tem_st and "ICMS" in partilha and partilha["ICMS"] > 0:
        pct_icms = partilha["ICMS"]
        ae = (ae * (1 - pct_icms)).quantize(D13, ROUND_HALF_UP)
        passos.append(
            f"ST detectada: parcela ICMS ({float(pct_icms):.2%}) removida da alíquota efetiva. "
            f"Novo alíquota efetiva = {float(ae):.13%}. "
            f"Motivo: o ICMS já foi recolhido pelo fornecedor na entrada."
        )
        partilha = _remover_tributo(partilha, "ICMS", passos)

    # ── Desenquadramento ICMS ─────────────────────────────────────────────────
    if icms_fora and not tem_st and "ICMS" in partilha and partilha["ICMS"] > 0:
        passos.append(
            "ICMS desenquadrado do Simples: a empresa recolhe ICMS separadamente (SEFAZ). "
            "A parcela de ICMS é removida do DAS."
        )
        partilha_pct = _remover_tributo(partilha, "ICMS", passos)
        total_pct = sum(partilha_pct.values())
        ae = (ae * total_pct).quantize(D13, ROUND_HALF_UP)
        partilha = partilha_pct

    # ── Desenquadramento ISS ──────────────────────────────────────────────────
    if iss_fora and "ISS" in partilha and partilha["ISS"] > 0:
        passos.append(
            "ISS fora do Simples: município não aderiu ou empresa excluída. "
            "ISS recolhido separadamente pela guia municipal."
        )
        partilha_pct = _remover_tributo(partilha, "ISS", passos)
        total_pct = sum(partilha_pct.values())
        ae = (ae * total_pct).quantize(D13, ROUND_HALF_UP)
        partilha = partilha_pct

    # ── Anexo IV: CPP sempre fora ─────────────────────────────────────────────
    if anexo_efetivo == "IV":
        passos.append(
            "Anexo IV: CPP (previdência patronal) NUNCA está no DAS — recolher via GPS separada. "
            "Isso não é desenquadramento, é a regra padrão do Anexo IV."
        )

    # ── DAS do segmento ───────────────────────────────────────────────────────
    das = (receita * ae).quantize(D2, ROUND_HALF_UP)
    passos.append(
        f"DAS = R$ {float(receita):,.2f} × {float(ae):.13%} = R$ {float(das):,.2f}"
    )

    # ── Partilha em valores ───────────────────────────────────────────────────
    partilha_val: Dict[str, Decimal] = {}
    for t, p in partilha.items():
        partilha_val[t] = (das * p).quantize(D2, ROUND_HALF_UP)

    return SegApurado(
        tipo=("Serviço" if anexo_efetivo in ("III","IV","V") else "Mercadoria"),
        anexo=anexo, anexo_efetivo=anexo_efetivo,
        tem_st=tem_st, receita=receita,
        faixa=faixa.num, aliq_nominal=faixa.aliq_nom, deducao=faixa.deducao,
        aliq_efetiva=ae, das=das, partilha=partilha_val, passos=passos,
    )

# ── Engine principal ──────────────────────────────────────────────────────────

def apurar(cfg: ConfigEmpresa, notas: List[NotaFiscal]) -> ResultadoEmpresa:
    alertas: List[str] = []

    # Validação RBT12
    if cfg.rbt12 > LIMITE_SIMPLES:
        alertas.append(
            f"RBT12 (R$ {float(cfg.rbt12):,.2f}) excede R$ 4.800.000 — "
            "empresa pode estar fora do Simples Nacional. Verifique o enquadramento."
        )

    # ── Filtra notas pelo CNPJ raiz (matriz e todas as filiais entram automaticamente) ──
    raiz_cfg = "".join(c for c in cfg.cnpj_raiz if c.isdigit())[:8].zfill(8)

    def pertence(n: NotaFiscal) -> bool:
        em = "".join(c for c in n.cnpj_emitente if c.isdigit())
        return len(em) >= 8 and em[:8] == raiz_cfg

    notas_emp = [n for n in notas if pertence(n) and n.tipo_op == "1"]

    n_canceladas   = sum(1 for n in notas_emp if n.cancelada)
    n_frete        = sum(1 for n in notas_emp if n.is_frete_cte and not n.cancelada)
    n_transf       = sum(1 for n in notas_emp if n.is_transferencia and not n.cancelada)
    n_dev          = sum(1 for n in notas_emp if n.is_devolucao and not n.cancelada)
    notas_validas  = [n for n in notas_emp if not n.cancelada and not n.is_frete_cte]

    # Alertas sobre notas
    if n_canceladas > 0:
        alertas.append(f"{n_canceladas} nota(s) cancelada(s) excluída(s) da receita.")
    if n_frete > 0:
        alertas.append(f"{n_frete} CT-e(s) excluído(s) — frete não entra na receita bruta do Simples.")
    if n_transf > 0:
        alertas.append(f"{n_transf} nota(s) de transferência entre estabelecimentos excluída(s).")
    if n_dev > 0:
        alertas.append(f"{n_dev} nota(s) de devolução — valor SUBTRAÍDO da receita do mês.")

    # ── Acumula receita por (tipo, tem_st) ────────────────────────────────────
    acumulado: Dict[tuple, Decimal] = {}
    for nota in notas_validas:
        sinal = Decimal("-1") if nota.is_devolucao else Decimal("1")
        for item in nota.itens:
            if item.tipo == "transferencia":
                continue
            k = (item.tipo, item.tem_st)
            acumulado[k] = acumulado.get(k, Decimal("0")) + sinal * item.valor

    # Aviso se receita for negativa (mais devoluções que vendas)
    for (tipo_seg, st_seg), v in acumulado.items():
        if v < 0:
            alertas.append(
                f"Receita de '{tipo_seg}' (ST={st_seg}) negativa: R$ {float(v):,.2f}. "
                "Devoluções superam as vendas neste segmento no mês."
            )

    # ── Serviços sem XML (valor manual) ───────────────────────────────────────
    if cfg.receita_servico_manual is not None and cfg.receita_servico_manual > 0:
        serv_segs = [s for s in cfg.segmentos if s.get("tipo") == "servico"]
        if not serv_segs:
            alertas.append(
                "Há **receita de serviço manual**, mas nenhum segmento **Serviço** foi configurado — "
                "esse valor não entrou no DAS. Inclua um segmento Serviço (ex.: Anexo III)."
            )
        else:
            sc0 = serv_segs[0]
            st_m = bool(sc0.get("tem_st", False))
            k = ("servico", st_m)
            acumulado[k] = acumulado.get(k, Decimal("0")) + cfg.receita_servico_manual
            alertas.append(
                f"Serviços **sem XML**: + {br(cfg.receita_servico_manual)} somados ao segmento serviço "
                f"(usa o 1º segmento Serviço: Anexo {sc0.get('anexo','?')}, ST={'sim' if st_m else 'não'})."
            )

    # ── Calcula DAS por segmento configurado ───────────────────────────────────
    segs_apurados: List[SegApurado] = []
    receita_total  = Decimal("0")
    das_total      = Decimal("0")
    tipos_usados   = set()

    merc_anex_12 = [
        s
        for s in cfg.segmentos
        if s.get("tipo") == "mercadoria" and s.get("anexo") in ("I", "II")
    ]
    um_so_merc_anexo_12 = len(merc_anex_12) == 1
    _split_merc_feito = False

    for sc in cfg.segmentos:
        tipo_cfg = sc.get("tipo","mercadoria")
        st_cfg   = sc.get("tem_st", False)
        anexo    = sc.get("anexo","I")

        # Um único segmento Mercadoria Anexo I ou II: reparte sozinha ST / não-ST
        # pelos itens (CST/CSOSN nos XML). CFOP não basta para ST — evita orphan e
        # dispensa dois segmentos manuais no caso mais comum.
        if (
            um_so_merc_anexo_12
            and not _split_merc_feito
            and tipo_cfg == "mercadoria"
            and anexo in ("I", "II")
        ):
            _split_merc_feito = True
            r_sem = acumulado.get(("mercadoria", False), Decimal("0"))
            r_com = acumulado.get(("mercadoria", True), Decimal("0"))
            if r_sem > 0 and r_com > 0:
                alertas.append(
                    "**Comércio (Anexo I ou II):** há receita **com** e **sem** ST nos XML. "
                    "Com um único segmento mercadoria, o sistema **apurou em duas linhas** "
                    "(como Seção I e II do PGDAS), usando **CST/CSOSN** dos itens — **não** o CFOP sozinho."
                )
            for st_key in (False, True):
                receita = acumulado.get(("mercadoria", st_key), Decimal("0"))
                if receita <= 0:
                    continue
                tipos_usados.add(("mercadoria", st_key))
                seg = _calcular_segmento(
                    receita, cfg.rbt12, anexo, st_key,
                    cfg.icms_fora_simples, cfg.iss_fora_simples, cfg.folha12,
                )
                seg.tipo = "Mercadoria"
                segs_apurados.append(seg)
                receita_total += receita
                das_total += seg.das
            continue

        # Match por (tipo, ST) dos XML; se vazio, tenta o outro bucket do mesmo tipo.
        # IMPORTANTE: a alíquota (retirada de ICMS na ST) deve seguir o bucket onde a
        # receita **realmente** está nos XML — não só o checkbox do segmento. Senão,
        # comércio só com itens ST (CSOSN 201 etc.) e segmento "sem ST" caía na alíquota
        # ~5% em vez da ~3,3% do PGDAS (Seção II).
        receita_ex = acumulado.get((tipo_cfg, st_cfg), Decimal("0"))
        receita_fb = acumulado.get((tipo_cfg, not st_cfg), Decimal("0"))
        if receita_ex > 0:
            receita = receita_ex
            st_efetivo = st_cfg
        elif receita_fb > 0:
            receita = receita_fb
            st_efetivo = not st_cfg
        else:
            continue

        if st_efetivo != st_cfg:
            alertas.append(
                f"Segmento **{tipo_cfg}** cadastrado com ST={'sim' if st_cfg else 'não'}, "
                f"mas a receita dos XML está toda em ST={'sim' if st_efetivo else 'não'}. "
                f"A **alíquota efetiva** foi calculada como **ST={'sim' if st_efetivo else 'não'}** "
                f"(igual ao critério dos itens da NF-e)."
            )

        tipos_usados.add((tipo_cfg, st_efetivo))

        seg = _calcular_segmento(
            receita, cfg.rbt12, anexo, st_efetivo,
            cfg.icms_fora_simples, cfg.iss_fora_simples, cfg.folha12,
        )
        seg.tipo = tipo_cfg.capitalize()
        segs_apurados.append(seg)
        receita_total += receita
        das_total     += seg.das

    # Avisos de receitas sem segmento configurado
    for (tipo_seg, st_seg), v in acumulado.items():
        if (tipo_seg, st_seg) not in tipos_usados and v > 0:
            if tipo_seg == "mercadoria":
                dica = (
                    "Com **um** segmento Mercadoria Anexo I ou II o app **já separa** ST pelo XML. "
                    "Se este aviso ainda aparece, costuma ser **mais de um** segmento mercadoria I/II à mão que não cobre todos os buckets — "
                    "use **Personalizado** com uma linha **só** para mercadoria I (ou II) **ou** duas linhas explícitas (ST sim / não). "
                    "ST vem do **CST/CSOSN** do item, não do CFOP."
                )
            else:
                dica = (
                    "Adicione um segmento **Serviço** (tipo e anexo conforme o caso) com ST alinhado ao que os XML indicam, "
                    "ou ajuste o segmento existente."
                )
            alertas.append(
                f"ATENÇÃO: receita de **'{tipo_seg}'** com **ST={'sim' if st_seg else 'não'}** = R$ {float(v):,.2f} "
                f"não tinha segmento correspondente e **não entrou no DAS**. "
                + dica
            )

    fator_r_val: Optional[Decimal] = None
    if cfg.folha12 is not None and cfg.rbt12 > 0:
        fator_r_val = (cfg.folha12 / cfg.rbt12).quantize(Decimal("0.0001"), ROUND_HALF_UP)

    # ── Receita por estabelecimento (matriz / filiais) pelos XML ───────────────
    rec_por_est: defaultdict[str, Decimal] = defaultdict(Decimal)
    qtd_por_est: defaultdict[str, int] = defaultdict(int)
    for n in notas_validas:
        k = norm_cnpj14_digits(n.cnpj_emitente)
        if not k:
            continue
        rec_por_est[k] += n.valor_receita
        qtd_por_est[k] += 1

    def _ord_estab(k: str) -> Tuple[int, str]:
        if len(k) < 12:
            return (1, k)
        return (0 if k[8:12] == "0001" else 1, k)

    est_rows: List[EstabelecimentoResumo] = [
        EstabelecimentoResumo(
            cnpj14=k,
            papel=papel_matriz_filial(k),
            receita=rec_por_est[k],
            notas=qtd_por_est[k],
        )
        for k in sorted(rec_por_est.keys(), key=_ord_estab)
    ]
    if cfg.receita_servico_manual is not None and cfg.receita_servico_manual > 0:
        est_rows.append(
            EstabelecimentoResumo(
                cnpj14="",
                papel="Serviço sem NF-e (valor manual)",
                receita=cfg.receita_servico_manual,
                notas=0,
            )
        )

    return ResultadoEmpresa(
        nome=rotulo_empresa(cfg), cnpj_raiz=cfg.cnpj_raiz, rbt12=cfg.rbt12,
        fator_r=fator_r_val,
        receita_total=receita_total, das_total=das_total,
        segmentos=segs_apurados,
        notas_validas=len(notas_validas), notas_canceladas=n_canceladas,
        notas_devolucao=n_dev, notas_frete=n_frete, notas_transferencia=n_transf,
        alertas=alertas,
        estabelecimentos=est_rows,
    )

def apurar_lote(configs: List[ConfigEmpresa], notas: List[NotaFiscal]) -> List[ResultadoEmpresa]:
    return [apurar(cfg, notas) for cfg in configs]


def _notas_saida_apuraveis_por_raiz(notas: List[NotaFiscal], raiz8: str) -> List[NotaFiscal]:
    """Saídas da raiz, não canceladas, sem CT-e de frete — mesmo recorte que entra na apuração."""
    rz = raiz8.zfill(8)
    out: List[NotaFiscal] = []
    for n in notas:
        if n.tipo_op != "1":
            continue
        em = "".join(c for c in n.cnpj_emitente if c.isdigit())
        if len(em) < 8 or em[:8] != rz:
            continue
        if n.cancelada or n.is_frete_cte:
            continue
        out.append(n)
    return out


def _raizes_emitentes_com_saida(notas: List[NotaFiscal]) -> List[str]:
    s: set[str] = set()
    for n in notas:
        if n.tipo_op != "1" or n.cancelada or n.is_frete_cte:
            continue
        em = "".join(c for c in n.cnpj_emitente if c.isdigit())
        if len(em) >= 8:
            s.add(em[:8])
    return sorted(s)


def acumulado_receita_tipo_st(notas_validas_raiz: List[NotaFiscal]) -> Dict[tuple, Decimal]:
    """Espelha a lógica de `apurar` para (tipo_item, tem_st) sem depender de ConfigEmpresa."""
    acumulado: Dict[tuple, Decimal] = {}
    for nota in notas_validas_raiz:
        sinal = Decimal("-1") if nota.is_devolucao else Decimal("1")
        for item in nota.itens:
            if item.tipo == "transferencia":
                continue
            k = (item.tipo, item.tem_st)
            acumulado[k] = acumulado.get(k, Decimal("0")) + sinal * item.valor
    return acumulado


def cfops_mais_frequentes(notas_raiz: List[NotaFiscal], limite: int = 18) -> str:
    ctr: Counter[str] = Counter()
    for n in notas_raiz:
        for cf in n.cfops:
            ctr[cf] += 1
    if not ctr:
        return "—"
    return " · ".join(f"{cf} ({cnt})" for cf, cnt in ctr.most_common(limite))


def texto_sugestao_conferencia_dominio(acum: Dict[tuple, Decimal]) -> str:
    """Texto curto para comparar cadastro no Domínio (anexos / ST / misto)."""
    m0 = acum.get(("mercadoria", False), Decimal("0"))
    m1 = acum.get(("mercadoria", True), Decimal("0"))
    s0 = acum.get(("servico", False), Decimal("0"))
    s1 = acum.get(("servico", True), Decimal("0"))
    merc = m0 + m1
    serv = s0 + s1
    if merc <= 0 and serv <= 0:
        return (
            "Não há receita de itens (mercadoria/serviço) neste recorte — só transferência, "
            "ou notas fora do critério."
        )
    blocos: List[str] = []
    if merc > 0 and serv > 0:
        blocos.append(
            "**Misto:** mercadoria **e** serviço nos XML. No Domínio costuma haver **mais de um anexo**; "
            "no app use **Comércio (I) + serviços (III)** (ou Personalizado)."
        )
    if merc > 0:
        if m0 > 0 and m1 > 0:
            blocos.append(
                "**Comércio Anexo I:** há venda **com** e **sem** ST (CSOSN nos itens). "
                "Um **único** segmento Mercadoria · Anexo I basta — o app **apura em duas linhas** (estilo Seção I / II PGDAS)."
            )
        elif m1 > 0:
            blocos.append(
                "**Comércio Anexo I com ST** nos itens — confira no Domínio se a atividade está na **Seção II** (substituição)."
            )
        else:
            blocos.append(
                "**Comércio sem ST** nos itens — confira **Seção I** ou equivalente no Domínio."
            )
    if serv > 0:
        blocos.append(
            "**Serviço** em NF-e — no Domínio confira **Anexo III** (ou IV/V conforme CNAE/atividade cadastrada)."
        )
    return " ".join(blocos)


# ── Config / pastas locais ───────────────────────────────────────────────────

CONFIG_JSON = Path(__file__).resolve().parent / "config_app.json"


@dataclass
class AppRuntimeConfig:
    """modo: upload | hibrido | pastas"""

    modo: str
    pastas_padrao: List[str] = field(default_factory=list)
    recursivo: bool = True

    @property
    def permite_upload(self) -> bool:
        return self.modo in ("upload", "hibrido")

    @property
    def permite_pastas(self) -> bool:
        return self.modo in ("hibrido", "pastas")

    @property
    def modo_label(self) -> str:
        return {"upload": "Somente upload", "hibrido": "Híbrido", "pastas": "Somente pastas locais"}.get(
            self.modo, self.modo
        )

    @property
    def perfil_execucao(self) -> str:
        """Texto curto para a sidebar: online (nuvem) vs híbrido/servidor neste PC."""
        if self.modo == "upload":
            return "Total online (upload no navegador)"
        if self.modo == "hibrido":
            return "Híbrido — servidor neste PC + pastas e/ou upload"
        return "Pastas locais — servidor neste PC (sem upload)"


def _json_load(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _truthy(v: Optional[str]) -> bool:
    if v is None:
        return True
    return str(v).strip().lower() in ("1", "true", "yes", "sim", "on")


def _parse_pastas_env(s: Optional[str]) -> List[str]:
    if not s or not str(s).strip():
        return []
    # aceita quebra de linha ou ;
    parts: List[str] = []
    for block in str(s).replace(";", "\n").splitlines():
        t = block.strip()
        if t:
            parts.append(t)
    return parts


def _secrets_get(key: str) -> Optional[str]:
    try:
        import streamlit as st  # noqa: WPS433

        if hasattr(st, "secrets") and key in st.secrets:
            v = st.secrets[key]
            return str(v) if v is not None else None
    except Exception:
        pass
    return None


def carregar_config() -> AppRuntimeConfig:
    modo = "upload"
    pastas: List[str] = []
    recursivo = True

    if CONFIG_JSON.exists():
        try:
            data = _json_load(CONFIG_JSON)
            modo = str(data.get("modo", modo)).strip().lower() or modo
            px = data.get("pastas_xml") or {}
            if isinstance(px, dict):
                pastas = [str(p).strip() for p in px.get("caminhos", []) if str(p).strip()]
                recursivo = bool(px.get("recursivo", True))
        except (json.JSONDecodeError, OSError):
            pass

    env_modo = os.environ.get("SN_MODO")
    if env_modo:
        modo = env_modo.strip().lower()

    env_pastas = os.environ.get("SN_PASTAS")
    if env_pastas:
        pastas = _parse_pastas_env(env_pastas)

    env_rec = os.environ.get("SN_RECURSIVO")
    if env_rec is not None:
        recursivo = _truthy(env_rec)

    sm = _secrets_get("SN_MODO")
    if sm:
        modo = sm.strip().lower()

    sp = _secrets_get("SN_PASTAS")
    if sp:
        pastas = _parse_pastas_env(sp)

    sr = _secrets_get("SN_RECURSIVO")
    if sr is not None:
        recursivo = _truthy(sr)

    if modo not in ("upload", "hibrido", "pastas"):
        modo = "upload"

    # Na nuvem, pastas locais não existem no servidor — força upload.
    if os.environ.get("SN_FORCAR_UPLOAD", "").strip().lower() in ("1", "true", "yes", "sim"):
        modo = "upload"
        pastas = []

    return AppRuntimeConfig(modo=modo, pastas_padrao=pastas, recursivo=recursivo)


def ambiente_so_web(cfg: AppRuntimeConfig) -> bool:
    """
    True = interface para usuário final na web: sem menções a disco local, D:\\, scripts ou servidor.
    Use SN_AMBIENTE=local no Garimpeiro para forçar textos completos de desenvolvimento.
    """
    if os.environ.get("SN_AMBIENTE", "").strip().lower() == "local":
        return False
    if os.environ.get("SN_AMBIENTE", "").strip().lower() == "online":
        return True
    if os.environ.get("STREAMLIT_CLOUD", "").strip() in ("1", "true", "True", "yes"):
        return True
    if cfg.modo == "upload":
        return True
    return False


def listar_arquivos_fiscais(caminhos: List[str], recursivo: bool) -> Tuple[List[Tuple[str, bytes]], List[str]]:
    """
    Retorna (lista de (nome_para_log, bytes), avisos).
    `nome_para_log` evita colisões quando há várias pastas.
    """
    saida: List[Tuple[str, bytes]] = []
    avisos: List[str] = []
    vistos: set[str] = set()

    for raw in caminhos:
        p = Path(raw).expanduser()
        try:
            p = p.resolve()
        except OSError:
            avisos.append(f"Caminho inválido ou inacessível: {raw}")
            continue

        if not p.exists():
            avisos.append(f"Não existe: {p}")
            continue

        if p.is_file():
            suf = p.suffix.lower()
            if suf not in (".xml", ".zip"):
                avisos.append(f"Ignorado (não é .xml/.zip): {p}")
                continue
            chave = str(p)
            if chave in vistos:
                continue
            vistos.add(chave)
            try:
                saida.append((p.name, p.read_bytes()))
            except OSError as e:
                avisos.append(f"Erro ao ler {p}: {e}")
            continue

        if p.is_dir():
            base_nome = p.name or str(p)
            if recursivo:
                iterador = p.rglob("*")
            else:
                iterador = p.glob("*")
            for f in iterador:
                if not f.is_file():
                    continue
                suf = f.suffix.lower()
                if suf not in (".xml", ".zip"):
                    continue
                chave = str(f.resolve())
                if chave in vistos:
                    continue
                vistos.add(chave)
                try:
                    rel = f.relative_to(p).as_posix()
                    nome_log = f"{base_nome}/{rel}"
                    saida.append((nome_log, f.read_bytes()))
                except OSError as e:
                    avisos.append(f"Erro ao ler {f}: {e}")

    return saida, avisos

# ── Interface Streamlit ─────────────────────────────────────────────────────
st.set_page_config(
    page_title="Apuração Simples Nacional",
    page_icon="📊",
    layout="wide",
)

# ── Helpers ───────────────────────────────────────────────────────────────────
def br(v, prefix="R$ ") -> str:
    try:
        s = f"{float(v):,.2f}".replace(",","X").replace(".",",").replace("X",".")
        return f"{prefix}{s}"
    except:
        return "—"

def pct(v) -> str:
    try: return f"{float(v)*100:.13f}%".replace(".",",")
    except: return "—"

def pct2(v) -> str:
    try: return f"{float(v)*100:.2f}%".replace(".",",")
    except: return "—"

def parse(txt: str) -> Decimal:
    t = txt.strip().replace("R$","").replace(" ","").replace(".","").replace(",",".")
    return Decimal(t) if t else Decimal("0")

def cnpj8(s: str) -> str:
    return "".join(c for c in s if c.isdigit())[:8]

def cnpj14(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def fmt_raiz8(r: str) -> str:
    """CNPJ raiz para exibir: XX.XXX.XXX"""
    d = "".join(c for c in (r or "") if c.isdigit())[:8]
    if len(d) != 8:
        return r or "—"
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}"


def norm_cnpj14_digits(s: str) -> str:
    """Normaliza para 14 dígitos (emitente nos XML)."""
    d = "".join(c for c in (s or "") if c.isdigit())
    if not d:
        return ""
    if len(d) >= 14:
        return d[:14]
    return d.zfill(14)


def fmt_cnpj14(s: str) -> str:
    """Exibe CNPJ completo: XX.XXX.XXX/XXXX-XX"""
    x = norm_cnpj14_digits(s)
    if len(x) != 14:
        return s or "—"
    return f"{x[0:2]}.{x[2:5]}.{x[5:8]}/{x[8:12]}-{x[12:14]}"


def papel_matriz_filial(cnpj14: str) -> str:
    """Heurística usual: ordem 0001 = matriz; demais = filial."""
    if len(cnpj14) < 12:
        return "Estabelecimento"
    est = cnpj14[8:12]
    if est == "0001":
        return "Matriz"
    return f"Filial (ordem {est})"


def normalizar_chave_44(s: str) -> str:
    d = re.sub(r"\D", "", str(s or ""))
    if len(d) >= 44:
        return d[-44:]
    return d


def ler_chaves_cancel_excel_bytes(raw: bytes) -> Tuple[set, List[str]]:
    """Lê coluna A; cada célula com 44 dígitos vira chave NFe."""
    avisos: List[str] = []
    chaves: set = set()
    bio = io.BytesIO(raw)
    try:
        df = pd.read_excel(bio, header=None, usecols=[0], engine="openpyxl")
    except Exception:
        try:
            bio.seek(0)
            df = pd.read_excel(bio, header=None, usecols=[0], engine="xlrd")
        except Exception as e:
            return set(), [f"Não foi possível ler a planilha (.xlsx ou .xls): {e}"]
    col0 = df.iloc[:, 0]
    for v in col0:
        if pd.isna(v):
            continue
        nk = normalizar_chave_44(str(v).strip())
        if len(nk) == 44:
            chaves.add(nk)
        elif nk:
            avisos.append(f"Ignorado (não tem 44 dígitos): {str(v)[:32]}…")
    return chaves, avisos


def aplicar_cancelamentos_planilha(notas: List[NotaFiscal], chaves: set) -> Tuple[int, List[str]]:
    """Marca cancelada se a chave da nota estiver no conjunto da planilha."""
    if not chaves or not notas:
        return 0, []
    rest = set(chaves)
    marcadas = 0
    for n in notas:
        kn = normalizar_chave_44(n.chave)
        if len(kn) != 44:
            continue
        if kn not in chaves:
            continue
        rest.discard(kn)
        if not n.cancelada:
            n.cancelada = True
            n.decisoes.append("CANCELADA — chave informada na planilha Excel (coluna A).")
            marcadas += 1
        elif not any("planilha Excel" in d for d in n.decisoes):
            n.decisoes.append("Chave confirmada também na planilha Excel (coluna A).")
    avisos: List[str] = []
    if rest:
        avisos.append(
            f"{len(rest)} chave(s) da planilha **não** têm nota correspondente no lote atual."
        )
    return marcadas, avisos


def reverter_cancelamentos_somente_planilha(notas: List[NotaFiscal]) -> None:
    """Remove efeito da planilha; mantém cancelamento vindo de XML/evento."""
    for n in notas:
        tem_xml = any("evento de cancelamento encontrado nos arquivos" in d for d in n.decisoes)
        n.decisoes = [d for d in n.decisoes if "planilha Excel" not in d]
        if not tem_xml:
            n.cancelada = False


# ── Estado de sessão ──────────────────────────────────────────────────────────
if "configs"    not in st.session_state: st.session_state.configs    = []
if "notas"      not in st.session_state: st.session_state.notas      = []
if "resultados" not in st.session_state: st.session_state.resultados = []
if "chaves_cancel_excel" not in st.session_state:
    st.session_state.chaves_cancel_excel = set()


def definir_notas_e_planilha(notas: List[NotaFiscal]) -> None:
    st.session_state.notas = notas
    ch = st.session_state.get("chaves_cancel_excel") or set()
    if ch:
        aplicar_cancelamentos_planilha(notas, ch)

RUN_CFG = carregar_config()
_SO_WEB = ambiente_so_web(RUN_CFG)


class _Painel:
    """Substitui o contexto de `st.tabs()` por um bloco vazio — tudo numa única página (sem barra de abas)."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ── Barra lateral ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("##### Simples Nacional")
    if _SO_WEB:
        st.caption("Envie os XML ou ZIP na secção **2. Carregar XMLs** (role a página).")
    else:
        st.caption(RUN_CFG.perfil_execucao)
        st.caption(f"XML: **{RUN_CFG.modo_label}**")
        st.divider()
        st.caption(
            "Nuvem: só upload. Neste PC: `py -m streamlit run app.py` (opcional: `SN_MODO=hibrido`)."
        )

# ── Título ────────────────────────────────────────────────────────────────────
st.title("📊 Apuração do Simples Nacional")
if _SO_WEB:
    st.caption(
        "Escritório Contábil · Os dados ficam nesta sessão do navegador até fechar esta janela."
    )
else:
    st.caption(
        "Escritório Contábil · Sem banco de dados · Fechar o browser reinicia tudo · "
        f"Origem XML: **{RUN_CFG.modo_label}** (`config_app.json`, secrets ou `SN_MODO`)"
    )

st.caption(
    "📍 **Uma tela só** — role para baixo: Cliente → XMLs → Calcular → Resultados → Guia."
)

with st.expander("💡 Como preencher para chegar num DAS como no PGDAS (ex.: Anexo I + ST)", expanded=False):
    st.markdown(
        """
| No PGDAS / documento | O que fazer neste app |
|---|---|
| **CNPJ** | Informe a **raiz (8 dígitos)** ou CNPJ completo (matriz e filiais do mesmo grupo entram juntas). |
| **RBT12** (12 meses anteriores ao mês da apuração) | Mesmo valor do PGDAS, ex.: `256852,76` — **não** é a receita só do mês. |
| **RPA / receita do período** | Vem da **soma dos XML** que você envia (saídas válidas do mês). |
| **Anexo I**, revenda com **substituição tributária** (Seção II) | Perfil **Só comércio — Anexo I** e marque **Mercadoria com ST**. |
| **Alíquota efetiva** (~3,29%) **≠ 7,3%** | 7,3% é a **nominal** da faixa; o DAS usa a **efetiva** `(RBT12×nominal−PD)÷RBT12` e, com ST, **retira a parcela de ICMS** — veja nominal vs efetiva na tabela de resultados. |

**Ordem:** secção **1** (cliente) → **2** (XML/ZIP do mês) → **3** (Calcular) → **4** (conferir DAS e partilha).
        """
    )

abas = [_Painel() for _ in range(5)]

# ══════════════════════════════════════════════════════════════════════════════
# SECÇÃO 1 — EMPRESAS
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("1. Cliente")
st.caption("Obrigatório: **CNPJ** e **RBT12**. Escolha o **perfil** — só abra *Mais opções* se precisar.")
with abas[0]:

    with st.form("nova_empresa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            cnpj_input = st.text_input(
                "CNPJ (raiz 8 dígitos ou completo) *",
                help="Matriz e filiais com a mesma raiz entram juntas nos XML.",
            )
            rbt12_txt = st.text_input(
                "RBT12 — 12 meses anteriores (R$) *",
                placeholder="256852,76",
                help="Igual ao PGDAS: receita acumulada dos 12 meses antes do mês que está apurando.",
            )
        with c2:
            perfil_id = st.selectbox(
                "Perfil *",
                [x[0] for x in OPTS_PERFIL_RAPIDO],
                format_func=lambda k: dict(OPTS_PERFIL_RAPIDO)[k],
                index=0,
                help="Define anexos e quantos segmentos. Troque só se a empresa não for o caso mais comum.",
            )
            st_comercio = False
            if perfil_id in ("com_i", "mix_i_iii"):
                st_comercio = st.checkbox(
                    "Mercadoria com **substituição tributária (ST)**",
                    value=False,
                    help="Marque se as vendas de mercadoria entram na Seção II do PGDAS (ICMS-ST).",
                )

        if perfil_id == "adv":
            st.markdown("**Segmentos (personalizado)**")
            n_segs = st.number_input("Quantos segmentos?", 1, 5, 1, key="n_segs_adv")
            segs_preview: List[dict] = []
            for i in range(int(n_segs)):
                ca, cb, cc = st.columns(3)
                tipo = ca.selectbox(
                    "Tipo",
                    ["mercadoria", "servico"],
                    key=f"t{i}",
                    format_func=lambda x: x.capitalize(),
                )
                anexo = cb.selectbox(
                    "Anexo",
                    list(ANEXOS_DESC.keys()),
                    key=f"a{i}",
                    format_func=lambda x: ANEXOS_DESC[x],
                )
                st_cb = cc.checkbox("ST?", key=f"s{i}", help="Só para mercadoria Anexo I ou II.")
                segs_preview.append({"tipo": tipo, "anexo": anexo, "tem_st": st_cb})
        else:
            segs_preview = []

        with st.expander("Mais opções (só se precisar)", expanded=False):
            nome_cli = st.text_input("Nome / apelido do cliente (opcional)", placeholder="Ex.: Loja Centro")
            folha12_txt = st.text_input(
                "Folha 12 meses (R$) — para Anexo **V** ou Fator R",
                placeholder="0,00",
                help="Anexo V: necessário para o Fator R. Comércio puro costuma ficar em branco.",
            )
            icms_fora = st.checkbox("ICMS **fora** do Simples (desenquadramento estadual)")
            iss_fora = st.checkbox("ISS **fora** do Simples (guia municipal)")
            receita_serv_txt = st.text_input(
                "Serviços **sem** XML (R$)",
                placeholder="0,00",
                help="Soma ao segmento de serviço (ex.: NFS-e em papel).",
            )

        salvar = st.form_submit_button("➕ Adicionar cliente", type="primary")
        if salvar:
            erros: List[str] = []
            if not cnpj_input.strip():
                erros.append("Informe o CNPJ.")
            try:
                rbt12 = parse(rbt12_txt)
                assert rbt12 > 0
            except Exception:
                erros.append("RBT12 inválido ou zerado.")
                rbt12 = Decimal("0")

            if perfil_id == "adv":
                segs_in = segs_preview
            else:
                segs_in = segmentos_perfil_rapido(perfil_id, st_comercio)

            folha12: Optional[Decimal] = None
            try:
                folha12 = parse(folha12_txt) if folha12_txt.strip() else None
            except Exception:
                erros.append("Valor da folha inválido.")

            if perfil_id == "srv_v" and (folha12 is None or folha12 <= 0):
                erros.append("Para **Anexo V**, informe a **Folha 12 meses** em *Mais opções* (ou use personalizado).")

            if erros:
                for e in erros:
                    st.error(e)
            else:
                rsm: Optional[Decimal] = None
                err_manual: List[str] = []
                try:
                    rsm = parse(receita_serv_txt) if receita_serv_txt.strip() else None
                    if rsm is not None and rsm < 0:
                        err_manual.append("Receita de serviço manual não pode ser negativa.")
                except Exception:
                    err_manual.append("Valor de serviços sem XML inválido.")
                if err_manual:
                    for e in err_manual:
                        st.error(e)
                else:
                    nova = ConfigEmpresa(
                        nome=(nome_cli or "").strip(),
                        cnpj_raiz=cnpj8(cnpj_input),
                        rbt12=rbt12,
                        segmentos=segs_in,
                        folha12=folha12,
                        receita_servico_manual=rsm if rsm and rsm > 0 else None,
                        icms_fora_simples=icms_fora,
                        iss_fora_simples=iss_fora,
                    )
                    st.session_state.configs.append(nova)
                    st.success(f"✅ {rotulo_empresa(nova)} adicionado!")
                    st.rerun()

    # Lista
    if st.session_state.configs:
        st.subheader(f"{len(st.session_state.configs)} cliente(s) com parâmetros")
        for i, cfg in enumerate(st.session_state.configs):
            segs_str = " + ".join(
                f"{s['tipo'].capitalize()} Anexo {s['anexo']}"
                + (" (ST)" if s["tem_st"] else "")
                for s in cfg.segmentos
            )
            col1, col2 = st.columns([6,1])
            flags = []
            if cfg.icms_fora_simples: flags.append("ICMS fora")
            if cfg.iss_fora_simples:  flags.append("ISS fora")
            if cfg.folha12:           flags.append(f"Folha {br(cfg.folha12)}")
            if cfg.receita_servico_manual:
                flags.append(f"Serv. manual {br(cfg.receita_servico_manual)}")
            col1.markdown(
                f"**{rotulo_empresa(cfg)}** · RBT12 {br(cfg.rbt12)} · "
                f"{segs_str}" + (f" · {' | '.join(flags)}" if flags else "")
            )
            if col2.button("🗑️", key=f"del{i}"):
                st.session_state.configs.pop(i); st.rerun()
    else:
        st.info("Nenhum CNPJ configurado ainda.")

# ══════════════════════════════════════════════════════════════════════════════
# SECÇÃO 2 — CARREGAR XMLs
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("2. Carregar XMLs e cancelamentos")
with abas[1]:
    st.info(
        "Aceita **XMLs soltos e ZIPs aninhados** (ZIP dentro de ZIP). "
        "O sistema detecta automaticamente NF-e, NFC-e, NFS-e, CT-e e **eventos de cancelamento** quando estão no mesmo lote."
    )

    with st.expander("Cancelamentos — preciso de XML de cancelada?", expanded=False):
        st.markdown(
            """
**Sem o arquivo de cancelamento, o app não “adivinha” cancelamento.**  
Ele só marca nota como cancelada se encontrar, no lote:

- o **evento de cancelamento** da NF-e (ex.: procEventoNFe / evento **110111** com a chave da nota), **ou**
- NF-e em que já conste o cancelamento de forma que o leitor identifique.

Se você enviar **só a NF-e original** e **não** o XML do evento de cancelamento, a nota continua **válida** no cálculo — porque o sistema não tem como saber que foi cancelada depois.

**O que fazer na prática:** ao baixar da SEFAZ ou do seu emissor, inclua na pasta/ZIP também os **XML de eventos** (cancelamento, carta de correção não cancela, mas cancelamento sim). Ou use o **pacote completo** do período que já traga notas + eventos juntos.

**Alternativa:** envie uma **planilha Excel** (coluna A com as **44 posições da chave** das notas canceladas) na seção abaixo — o app marca o cancelamento ao casar a chave com as notas já carregadas.
            """
        )

    st.subheader("Cancelamentos por planilha Excel")
    st.caption("Coluna **A**: uma chave de NF-e por linha (44 dígitos, com ou sem formatação). Depois use **Carregar chaves**.")
    xls_cancel = st.file_uploader(
        "Arquivo Excel (.xlsx ou .xls)",
        type=["xlsx", "xls"],
        key="upload_chaves_cancel",
    )
    bx1, bx2 = st.columns(2)
    with bx1:
        if st.button("📎 Carregar chaves e aplicar aos XMLs", type="secondary"):
            if not xls_cancel:
                st.error("Selecione um arquivo Excel.")
            else:
                raw = xls_cancel.getvalue()
                chaves, avisos = ler_chaves_cancel_excel_bytes(raw)
                for a in avisos[:15]:
                    st.warning(a)
                if avisos and len(avisos) > 15:
                    st.caption(f"(+{len(avisos) - 15} aviso(s) omitidos)")
                st.session_state.chaves_cancel_excel = chaves
                if st.session_state.notas:
                    reverter_cancelamentos_somente_planilha(st.session_state.notas)
                    m, extra = aplicar_cancelamentos_planilha(st.session_state.notas, chaves)
                    for e in extra:
                        st.info(e)
                    st.success(
                        f"**{len(chaves)}** chave(s) na planilha · **{m}** nota(s) marcada(s) como cancelada."
                    )
                else:
                    st.success(
                        f"**{len(chaves)}** chave(s) guardadas. Carregue os XMLs depois — as chaves serão aplicadas automaticamente."
                    )
                st.rerun()
    with bx2:
        if st.button("Limpar planilha de chaves"):
            st.session_state.chaves_cancel_excel = set()
            if st.session_state.notas:
                reverter_cancelamentos_somente_planilha(st.session_state.notas)
            st.rerun()
    if st.session_state.chaves_cancel_excel:
        st.caption(f"Chaves ativas na planilha: **{len(st.session_state.chaves_cancel_excel)}**")

    if RUN_CFG.modo == "upload":
        if not _SO_WEB:
            st.success(
                "**Modo somente upload** — ideal para Streamlit Cloud / GitHub. "
                "Os arquivos vêm só do navegador; o servidor não acessa pastas do seu PC."
            )
    elif RUN_CFG.modo == "hibrido":
        st.success(
            "**Modo híbrido** — use pastas neste computador **e/ou** upload. "
            "Útil com `streamlit run` na sua máquina."
        )
    else:
        st.warning(
            "**Modo somente pastas** — não há upload; informe caminhos válidos abaixo. "
            "Indicado para automação local."
        )

    if RUN_CFG.permite_upload:
        uploaded = st.file_uploader(
            "Enviar arquivos pelo navegador",
            type=["xml", "zip"],
            accept_multiple_files=True,
        )
        if uploaded and st.button("📂 Processar arquivos enviados", type="primary"):
            with st.spinner("Lendo XMLs..."):
                arquivos = [(f.name, f.read()) for f in uploaded]
                notas = ler_arquivos(arquivos)
                definir_notas_e_planilha(notas)
            st.success(f"✅ {len(notas)} documento(s) lido(s).")

    if RUN_CFG.permite_pastas:
        st.subheader("Pastas ou arquivos no computador (servidor Streamlit)")
        st.caption(
            "Caminhos absolutos no Windows, um por linha. "
            "Pastas do `config_app.json` aparecem como padrão; você pode editar antes de processar."
        )
        default_txt = "\n".join(RUN_CFG.pastas_padrao)
        caminhos_txt = st.text_area(
            "Caminhos (pastas ou arquivos .xml / .zip)",
            value=default_txt,
            height=120,
            placeholder="D:\\Contabilidade\\XMLs\\ClienteX",
            key="paths_xml_local",
        )
        c1, c2 = st.columns(2)
        rec_user = c1.checkbox(
            "Buscar subpastas (recursivo)",
            value=RUN_CFG.recursivo,
            key="rec_xml_local",
        )
        if c2.button("📁 Processar pastas locais", type="primary"):
            paths = [ln.strip() for ln in caminhos_txt.splitlines() if ln.strip()]
            if not paths:
                st.error("Informe pelo menos um caminho.")
            else:
                with st.spinner("Lendo arquivos do disco..."):
                    arquivos, avisos = listar_arquivos_fiscais(paths, rec_user)
                    for a in avisos:
                        st.warning(a)
                    if not arquivos:
                        st.error("Nenhum .xml ou .zip encontrado nesses caminhos.")
                    else:
                        notas = ler_arquivos(arquivos)
                        definir_notas_e_planilha(notas)
                        st.success(
                            f"✅ {len(notas)} documento(s) a partir de **{len(arquivos)}** arquivo(s) no disco."
                        )

    notas: List[NotaFiscal] = st.session_state.notas
    if notas:
        # Contadores
        c = {
            "NF-e (55)":    sum(1 for n in notas if n.modelo=="55"),
            "NFC-e (65)":   sum(1 for n in notas if n.modelo=="65"),
            "NFS-e":        sum(1 for n in notas if n.modelo=="NFSe"),
            "CT-e":         sum(1 for n in notas if n.modelo=="57"),
            "Canceladas":   sum(1 for n in notas if n.cancelada),
            "Devoluções":   sum(1 for n in notas if n.is_devolucao and not n.cancelada),
            "Transferências": sum(1 for n in notas if n.is_transferencia),
        }
        cols = st.columns(len(c))
        for col, (label, val) in zip(cols, c.items()):
            col.metric(label, val)

        st.subheader("Conferência com Domínio (ou outro ERP)")
        st.caption(
            "Resumo **automático** dos XML — **sem** abrir nota a nota: tipo de receita, ST pelos itens "
            "(CSOSN/CST) e CFOPs frequentes, para bater com o **cadastro de anexos** no seu sistema."
        )
        for rz in _raizes_emitentes_com_saida(notas):
            nvr = _notas_saida_apuraveis_por_raiz(notas, rz)
            ac_dom = acumulado_receita_tipo_st(nvr)
            with st.container():
                st.markdown(f"##### CNPJ raiz **{fmt_raiz8(rz)}** — {len(nvr)} nota(s) de saída (apuráveis)")
                lin_dom = []
                for (tipo, stb), val in sorted(ac_dom.items(), key=lambda x: (x[0][0], x[0][1])):
                    if val == 0:
                        continue
                    lin_dom.append({
                        "Tipo (pelo item)": tipo.capitalize(),
                        "ST": "Sim" if stb else "Não",
                        "Receita no lote": br(val),
                    })
                if lin_dom:
                    st.dataframe(pd.DataFrame(lin_dom), use_container_width=True, hide_index=True)
                st.info(texto_sugestao_conferencia_dominio(ac_dom))
                st.caption("**CFOPs mais frequentes:** " + cfops_mais_frequentes(nvr))
                st.divider()

        with st.expander("🔍 Ver todas as notas lidas (com decisões do sistema)"):
            linhas = []
            for n in notas:
                status = []
                if n.cancelada:        status.append("CANCELADA")
                if n.is_devolucao:     status.append("DEVOLUÇÃO")
                if n.is_transferencia: status.append("TRANSFERÊNCIA")
                if n.is_frete_cte:     status.append("FRETE (excluído)")
                linhas.append({
                    "Modelo":    n.modelo,
                    "Emitente":  n.cnpj_emitente,
                    "Valor":     br(n.valor_total),
                    "CFOPs":     ", ".join(dict.fromkeys(n.cfops))[:50],
                    "ST":        "Sim" if n.tem_st else "Não",
                    "Status":    ", ".join(status) or "OK",
                    "Decisão":   n.decisoes[0][:80] if n.decisoes else "",
                })
            st.dataframe(pd.DataFrame(linhas), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECÇÃO 3 — CALCULAR
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("3. Calcular DAS")
with abas[2]:
    ne = len(st.session_state.configs)
    nn = len(st.session_state.notas)
    st.metric("Clientes (CNPJ) configurados", ne)
    st.metric("XMLs carregados", nn)

    if ne == 0:
        st.warning("Informe pelo menos um CNPJ na secção **1. Cliente** acima.")
    elif nn == 0:
        st.warning("Carregue os XMLs na secção **2.** acima.")
    else:
        if st.button("🚀 Calcular DAS de todos os clientes", type="primary"):
            with st.spinner("Calculando..."):
                resultados = apurar_lote(st.session_state.configs, st.session_state.notas)
                st.session_state.resultados = resultados
            st.success("✅ Concluído! Os resultados aparecem na secção **4** abaixo.")

# ══════════════════════════════════════════════════════════════════════════════
# SECÇÃO 4 — RESULTADOS
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("4. Resultados")
with abas[3]:
    resultados: List[ResultadoEmpresa] = st.session_state.resultados
    if not resultados:
        st.info("Quando tiver cliente + XMLs, use **Calcular DAS** na secção 3; o resumo aparece aqui.")
    else:

        # ── Resumo geral ──────────────────────────────────────────────────────────
        st.subheader("Resumo por CNPJ")
        linhas_resumo = []
        for r in resultados:
            linha = {
                "CNPJ raiz":     fmt_raiz8(r.cnpj_raiz),
                "Cliente":       r.nome,
                "RBT12":         br(r.rbt12),
                "Notas válidas": r.notas_validas,
                "Canceladas":    r.notas_canceladas,
                "Devoluções":    r.notas_devolucao,
                "Receita total": br(r.receita_total),
                "DAS total":     br(r.das_total),
            }
            if r.fator_r is not None:
                linha["Fator R"] = f"{float(r.fator_r)*100:.2f}%".replace(".", ",")
            linha["Estab. (XML)"] = sum(1 for e in r.estabelecimentos if e.cnpj14)
            linhas_resumo.append(linha)

        st.dataframe(pd.DataFrame(linhas_resumo), use_container_width=True)
        st.metric("Total DAS (todos os clientes)", br(sum(r.das_total for r in resultados)))

        st.subheader("Detalhe por CNPJ, segmento e alíquota")
        st.caption(
            "Uma linha por combinação de tipo de receita + anexo usado no cálculo: faixa, alíquota nominal, "
            "alíquota efetiva (PGDAS), receita e DAS do segmento."
        )
        linhas_det = []
        for r in resultados:
            for seg in r.segmentos:
                linhas_det.append({
                    "CNPJ raiz":        fmt_raiz8(r.cnpj_raiz),
                    "Tipo receita":     seg.tipo,
                    "Anexo cadastro":   seg.anexo,
                    "Anexo efetivo":    seg.anexo_efetivo,
                    "Atividade (tabela)": ANEXOS_DESC.get(seg.anexo_efetivo, ""),
                    "ST":               "Sim" if seg.tem_st else "Não",
                    "Faixa RBT12":      f"{seg.faixa}ª",
                    "Alíq. nominal":    pct(seg.aliq_nominal),
                    "Parcela deduzir":  br(seg.deducao),
                    "Alíq. efetiva":    pct(seg.aliq_efetiva),
                    "Receita segmento": br(seg.receita),
                    "DAS segmento":     br(seg.das),
                })
        if linhas_det:
            st.dataframe(pd.DataFrame(linhas_det), use_container_width=True)
        else:
            st.warning("Nenhum segmento apurado — verifique segmentos na secção 1 e XMLs na secção 2.")

        st.divider()

        # ── Detalhe por cliente ───────────────────────────────────────────────────
        for r in resultados:

            titulo = f"📋 {r.nome}  —  DAS {br(r.das_total)}"

            with st.expander(titulo, expanded=False):

                # Alertas
                for al in r.alertas:
                    st.warning(al)

                # Métricas — DAS único na raiz (PGDAS)
                st.markdown(f"### DAS consolidado (matriz + filiais): **{br(r.das_total)}**")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Receita total (apurada)", br(r.receita_total))
                c2.metric("DAS (único na raiz)",     br(r.das_total))
                c3.metric("Notas válidas",  r.notas_validas)
                c4.metric("Devoluções",     r.notas_devolucao)
                if r.fator_r is not None:
                    st.caption(f"Fator R (folha ÷ RBT12): **{float(r.fator_r)*100:.4f}%**".replace(".", ","))

                if r.estabelecimentos:
                    st.subheader("Receita por estabelecimento (matriz e filiais)")
                    st.caption(
                        "Valores extraídos dos XML por **CNPJ completo** do emitente. "
                        "Ordem **0001** tratada como matriz (regra usual)."
                    )
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    "Papel": e.papel,
                                    "CNPJ": fmt_cnpj14(e.cnpj14) if e.cnpj14 else "—",
                                    "Receita no mês": br(e.receita),
                                    "Notas": e.notas,
                                }
                                for e in r.estabelecimentos
                            ]
                        ),
                        use_container_width=True,
                    )

                # Segmentos
                for seg in r.segmentos:
                    st.markdown(f"---")
                    st.markdown(
                        f"**{seg.tipo} · Anexo {seg.anexo_efetivo}**"
                        + (" *(Fator R aplicado)*" if seg.anexo != seg.anexo_efetivo else "")
                        + (" · (ST)" if seg.tem_st else "")
                    )
                    sc1, sc2, sc3, sc4 = st.columns(4)
                    sc1.metric("Receita do segmento", br(seg.receita))
                    sc2.metric(f"Faixa",              f"{seg.faixa}ª")
                    sc3.metric("Alíq. efetiva",       pct(seg.aliq_efetiva))
                    sc4.metric("DAS do segmento",     br(seg.das))

                    # Passo a passo do cálculo — PEDAGÓGICO
                    with st.expander("📖 Como o sistema chegou nesse valor (passo a passo)"):
                        for i, passo in enumerate(seg.passos, 1):
                            st.markdown(f"**Passo {i}:** {passo}")

                    # Partilha
                    with st.expander("💰 Partilha por tributo"):
                        df_p = pd.DataFrame([
                            {"Tributo": t, "% na partilha": pct2(p/seg.das) if seg.das > 0 else "0%",
                             "Valor": br(p)}
                            for t in TRIBUTOS_ORDEM if (p := seg.partilha.get(t)) is not None
                        ])
                        st.table(df_p)

                # Notas desta empresa
                notas_all: List[NotaFiscal] = st.session_state.notas
                raiz_r = "".join(c for c in r.cnpj_raiz if c.isdigit())[:8].zfill(8)

                def pertence_emp(n: NotaFiscal) -> bool:
                    em = "".join(c for c in n.cnpj_emitente if c.isdigit())
                    return len(em) >= 8 and em[:8] == raiz_r

                notas_emp = [n for n in notas_all if pertence_emp(n) and n.tipo_op == "1"]
                with st.expander(f"🗂️ {len(notas_emp)} nota(s) desta empresa"):
                    linhas_n = []
                    for n in notas_emp:
                        status = []
                        if n.cancelada:        status.append("CANCELADA")
                        if n.is_devolucao:     status.append("DEVOLUÇÃO (-)")
                        if n.is_transferencia: status.append("TRANSFERÊNCIA (excluída)")
                        if n.is_frete_cte:     status.append("FRETE (excluído)")
                        linhas_n.append({
                            "Modelo":    n.modelo,
                            "Emitente":  n.cnpj_emitente,
                            "Valor":     br(n.valor_total),
                            "Na receita":br(n.valor_receita),
                            "CFOPs":     ", ".join(dict.fromkeys(n.cfops))[:50],
                            "ST":        "Sim" if n.tem_st else "Não",
                            "Status":    ", ".join(status) or "OK",
                        })
                    st.dataframe(pd.DataFrame(linhas_n), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECÇÃO 5 — GUIA DE REGRAS
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.subheader("5. Guia de regras")
with abas[4]:
    st.caption("Consulte quando precisar. O resumo numérico está na secção **4. Resultados** acima.")

    tema = st.selectbox("Escolha o tema:", [
        "O que entra na receita bruta",
        "CFOPs: entra ou não entra?",
        "Substituição Tributária (ST)",
        "Fator R (Anexo III vs V)",
        "Desenquadramento ICMS/ISS",
        "Matriz e filial",
        "A fórmula do DAS explicada",
        "Diferenças entre sistemas (conferência manual)",
    ])

    if tema == "O que entra na receita bruta":
        st.markdown("""
### O que ENTRA na receita bruta

| O que é | Entra? | Por quê |
|---|---|---|
| Venda de mercadoria (NF-e 55 / NFC-e 65) | ✅ Sim | Operação principal |
| Prestação de serviço (NFS-e) | ✅ Sim | Operação principal |
| Venda com ST (ICMS já pago) | ✅ Sim | Entra na base; só a alíquota é reduzida |
| Receita de filiais | ✅ Sim | Consolida na matriz |

### O que **não** entra como “venda positiva” — e mesmo assim **muda o total** do mês

Na coluna “Entra?” abaixo, **“Não”** quer dizer: **não soma como receita de venda/prestação a tributar** — não é “ignora o movimento”. O **faturado apurado no mês** (base do DAS) **muda sim** quando há devolução ou cancelamento.

| O que é | Entra como receita (+)? | O que acontece no total do mês |
|---|---|---|
| **Devolução** de venda (CFOP de devolução) | ❌ Não | **Subtrai** valores da receita bruta do período — estorna venda já contada em mês anterior ou no mesmo mês. |
| **Nota cancelada** | ❌ Não | **Exclui** a operação: a nota **não integra** a receita bruta (não há “venda válida” a tributar). O total do mês **fica menor** do que seria se a nota ainda entrasse. |
| Venda de ativo imobilizado | ❌ Não | Não é receita operacional do Simples |
| Transferência entre estabelecimentos | ❌ Não | Não é venda — movimentação interna |
| CT-e de frete (frete incluso na NF-e) | ❌ Não | Já está no valor da mercadoria na NF-e |
| Receita financeira | ❌ Não | Salvo instituições financeiras |

**Devolução × cancelada:** devolução é **movimento espelho** (menos na base). Cancelada é **anulação** — o sistema **não** trata como “menos uma venda” na mesma linha contábil; **simplesmente não conta** a nota cancelada na receita (efeito no total: também reduz o que entra no DAS).

> **Regra de ouro:** a receita bruta do Simples é o **saldo** das operações que **geram** receita tributável no período, respeitando devoluções e excluindo o que não é venda válida (ex.: cancelada, transferência).  
> O Simples não “desconta imposto” da base — a alíquota já embute a tributação.
        """)

    elif tema == "CFOPs: entra ou não entra?":
        st.markdown("""
### CFOPs que ENTRAM na receita bruta (saídas de venda)

- **5.101 / 6.101** — Venda de produção própria (indústria)
- **5.102 / 6.102** — Venda de mercadoria adquirida para revenda ← o mais comum no comércio
- **5.405 / 6.405** — Venda com ST (ICMS cobrado anteriormente)
- **5.933 / 6.933** — Prestação de serviço dentro de NF-e
- **5.124 / 6.124** — Industrialização por terceiros

### CFOPs que NÃO entram

- **5.352 / 6.352** — Transferência para filial ← muito comum o erro de incluir
- **1.201 / 2.201** — Devolução de venda recebida (entrada)
- **5.201 / 6.201** — Devolução de compra (saída) ← não é venda
- **5.551 / 6.551** — Venda de ativo imobilizado
- **5.910** — Remessa em bonificação (sem valor fiscal)

### CFOP misto na mesma nota

Uma NF-e pode ter itens com CFOP 5.102 (mercadoria) e 5.933 (serviço).  
Nesse caso:
1. Some os valores de cada tipo separadamente
2. Calcule o DAS de mercadoria com o Anexo I (ou II)
3. Calcule o DAS de serviço com o Anexo III (ou IV)
4. Some os dois DAS

> **Dica prática:** o CFOP começa com 1 ou 2 = entrada, com 5 ou 6 = saída.  
> Saída dentro do estado = 5.xxx | Saída interestadual = 6.xxx
        """)

    elif tema == "Substituição Tributária (ST)":
        st.markdown("""
### O que é ST no Simples Nacional

Quando uma empresa compra mercadoria e o fornecedor (indústria/atacado) já recolheu o ICMS 
antecipadamente, a empresa não precisa pagar ICMS de novo na saída. 
Por isso, a parcela de ICMS é **removida da alíquota efetiva do DAS** para essas vendas.

### Como identificar ST no XML

**CFOP não define ST sozinho.** Existem CFOPs que *em geral* acompanham ST (ex.: 5.405), mas a regra fiscal e o que este app usa é o **CST/CSOSN (ou CST)** de **cada item** — o mesmo CFOP pode aparecer com ou sem ST.

No XML da NF-e, em cada item `<det>`, dentro do bloco `<ICMS>`:

| CSOSN (Simples) | Significa | ST? |
|---|---|---|
| 201 | Tributada com permissão de crédito + ST | ✅ Sim |
| 202 | Sem permissão de crédito + ST | ✅ Sim |
| 203 | Isenta + ST | ✅ Sim |
| 500 | ICMS cobrado por ST anteriormente | ✅ Sim |
| 101, 102, 400 | Tributação normal sem ST | ❌ Não |
| 900 | Outros — analisar caso a caso | ⚠️ Verificar |

### A matemática da ST

```
Alíq. efetiva normal     = 7,228%
Parcela ICMS faixa 3     = 33,5%
Alíq. efetiva com ST     = 7,228% × (1 − 33,5%) = 4,807%
```

### Cuidados importantes

- ST é **por item** — a mesma nota pode ter itens com e sem ST
- Só se aplica ao **Anexo I** (comércio) e **Anexo II** (indústria)
- Serviços (III, IV, V) **não têm ST**
- A redução só vale se o fornecedor **realmente recolheu** o ICMS-ST

> **Erro mais frequente:** aplicar ST numa empresa que compra de fornecedores 
> que não recolheram o imposto. Confirme nas notas de entrada.
        """)

    elif tema == "Fator R (Anexo III vs V)":
        st.markdown("""
### O que é o Fator R

Para serviços que podem alternar entre Anexo III e V, a escolha depende de:

```
Fator R = Folha de Pagamento (12 meses) ÷ RBT12

≥ 28% → Anexo III (alíquota menor — recompensa quem tem mais funcionários)
< 28% → Anexo V (alíquota maior)
```

### O que entra na folha de pagamento para o Fator R

| Item | Entra? |
|---|---|
| Salários brutos (CLT) | ✅ Sim |
| Pró-labore dos sócios | ✅ Sim |
| INSS patronal (20% ou Simples) | ✅ Sim |
| FGTS (8%) | ✅ Sim |
| 13º salário e férias proporcionais | ✅ Sim |
| Salário líquido (já descontado) | ❌ Não — use o bruto |

### Atividades que usam Fator R

TI e software, engenharia, arquitetura, medicina, odontologia, psicologia, 
fisioterapia, fonoaudiologia, contabilidade, auditoria, economia, 
jornalismo, publicidade, veterinária.

### Atividades que NÃO usam Fator R (vão direto para Anexo IV)

Limpeza, vigilância, conservação, obras civis, serviços advocatícios.

> **Erro mais frequente:** calcular o Fator R sem incluir o pró-labore dos sócios 
> ou usando salário líquido em vez do bruto. Isso faz o Fator R cair abaixo de 28% 
> indevidamente, jogando a empresa para o Anexo V (alíquota mais alta).
        """)

    elif tema == "Desenquadramento ICMS/ISS":
        st.markdown("""
### O que é o desenquadramento parcial

A empresa continua no Simples Nacional mas o Estado ou Município a **exclui** 
do ICMS ou ISS dentro do Simples. Ela passa a recolher esse imposto separadamente.

### Desenquadramento do ICMS (Estado)

- ICMS sai do DAS
- Empresa recolhe ICMS pelo regime normal (GIA, SPED, guia SEFAZ)
- A alíquota efetiva do DAS fica menor (sem ICMS)
- Como saber: SEFAZ notifica; aparece no PGDAS como "ICMS fora do Simples"

### Desenquadramento do ISS (Município)

- ISS sai do DAS
- Empresa recolhe ISS pela guia municipal
- Acontece quando o município não aderiu ao Simples para ISS

### Não confunda com o Anexo IV

No Anexo IV, o **CPP (previdência patronal) nunca está no DAS** — 
isso não é desenquadramento, é a regra padrão do Anexo. 
A empresa recolhe CPP via GPS separada todos os meses.

> **Como tratar no app:** marque o flag correspondente na configuração da empresa.
> O sistema remove a parcela do tributo da alíquota e redistribui o restante proporcionalmente.
        """)

    elif tema == "Matriz e filial":
        st.markdown("""
### Regra fundamental do Simples Nacional

**Um único DAS** é emitido pela **matriz** (CNPJ raiz), consolidando todas as filiais.

### CNPJ raiz = 8 primeiros dígitos

```
Matriz:  12.345.678/0001-99  → raiz: 12345678
Filial 1: 12.345.678/0002-70  → raiz: 12345678  ← mesmo grupo
Filial 2: 12.345.678/0003-51  → raiz: 12345678  ← mesmo grupo
```

### O que consolida

- RBT12 = soma de todas as receitas (matriz + todas as filiais)
- DAS = calculado sobre o total consolidado
- O PGDAS é preenchido pela matriz

### O que NÃO soma

- Transferências entre os estabelecimentos (CFOP 5.352/6.352)
  → são movimentações internas, não vendas

> **Erro grave:** incluir notas de transferência como venda. Inflaria o RBT12 
> e poderia jogar a empresa para uma faixa maior, pagando mais imposto indevidamente.
        """)

    elif tema == "A fórmula do DAS explicada":
        st.markdown("""
### Passo 1 — RBT12 (base da faixa)

Receita Bruta dos **12 meses anteriores** ao mês de apuração.  
*Não inclui o mês atual. Some matriz + filiais.*

### Passo 2 — Encontrar a faixa

Com o RBT12, localiza a faixa na tabela do anexo correspondente.

### Passo 3 — Alíquota efetiva

```
Alíq. efetiva = (RBT12 × Alíq. nominal − Parcela a deduzir) ÷ RBT12
```

Exemplo: RBT12 = R$ 500.000, Anexo I, Faixa 3 (9,5%, dedução R$ 13.860)
```
(500.000 × 0,095 − 13.860) ÷ 500.000 = 7,228%
```

O PGDAS usa **13 casas decimais** nessa divisão — por isso pequenas diferenças 
entre sistemas são normais (centavos).

### Passo 4 — DAS do mês

```
DAS = Receita do mês × Alíquota efetiva
```

Se a receita do mês foi R$ 45.000:
```
45.000 × 7,228% = R$ 3.252,60
```

### Passo 5 — Ajustes especiais

- ST: multiplica a alíquota por (1 − % ICMS da faixa)
- Fator R ≥ 28%: usa tabela do Anexo III
- ICMS/ISS fora: remove a parcela do tributo
        """)

    elif tema == "Diferenças entre sistemas (conferência manual)":
        st.markdown("""
### Conferir com outro sistema (sem campo automático)

Este app **não importa** valores de outros programas: você sobe os XML, vê o **resumo por CNPJ e por segmento/anexo**
e compara com o que quiser **no olho** ou na sua planilha.

### Causas comuns quando dois sistemas divergem

| Causa | Onde olhar |
|---|---|
| Nota em um sistema e não no outro | Lista de notas por CNPJ (secção **4. Resultados**) |
| Arredondamento da alíquota efetiva | Diferença de centavos — frequente |
| ST diferente | CSOSN dos itens no XML |
| Fator R / folha | Valores informados na secção **1. Cliente** |
| Transferência como venda | CFOPs 5.352/6.352 |
| Frete duplicado | CT-e + frete na NF-e |

> Use a tabela **Detalhe por CNPJ, segmento e alíquota** para bater alíquota nominal, efetiva e DAS por recorte.
        """)
