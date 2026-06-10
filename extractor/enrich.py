"""Capa GENERADA (best-effort) — enriquecimiento para mejorar el recall del RAG.

⚠️  Contenido generado por un LLM. NO es texto oficial ni fuente de cita. Su
único propósito es AYUDAR A RECUPERAR la unidad correcta cuando el usuario
pregunta con lenguaje coloquial ("¿multa por no facturar?", "¿qué puedo
deducir?"). La respuesta y la cita SIEMPRE provienen del texto fiel y de los
pasajes, nunca de aquí.

Disciplina de cuarentena:
- Vive en `metadata/<clave>/generado/`, separado de las capas deterministas.
- Cada archivo lleva un bloque `_generado` con el modelo y un `hash_texto` para
  regenerar solo cuando el texto de la unidad cambió.
- La llamada al LLM se inyecta (`call`): producción usa Anthropic/OpenAI, los
  tests un doble determinista. Funciona para artículos, reglas y criterios.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .pasajes import _bloques
from .registro import Documento

SCHEMA_VERSION = 1
ADVERTENCIA = (
    "Contenido generado por IA como AYUDA DE RECUPERACIÓN. No es texto oficial "
    "ni fuente de cita; la verdad está en el archivo de texto de la unidad."
)
CAMPOS_LISTA = ("temas", "terminos_coloquiales", "preguntas_ejemplo")
CAMPOS_TEXTO = ("denominacion_comun", "resumen")

DEFAULT_MODELS = {
    "anthropic": "claude-opus-4-8",     # económico para volumen: claude-haiku-4-5
    "openai": "gpt-4o-mini",
}


def texto_plano(unidad) -> str:
    """Texto de la unidad sin notas de reforma (lo que ve el LLM)."""
    return "\n\n".join(_bloques(unidad.cuerpo, unidad.etiqueta))


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_prompt(descriptor: str, plain_text: str, contexto: str = "") -> str:
    # La ubicación jerárquica (Título/Capítulo/Sección) suele traer el NOMBRE del
    # régimen/tema, que no aparece en el cuerpo del artículo. Dárselo al modelo
    # evita que lo infiera de su memoria (y se equivoque: p. ej. etiquetar el
    # Régimen Simplificado de Confianza como el derogado RIF).
    ubicacion = f"\nUbicación en la ley (úsala para situar el tema): {contexto}\n" if contexto else ""
    return f"""Eres un asistente que prepara METADATOS DE BÚSQUEDA para un buscador
de legislación fiscal mexicana. NO interpretas la ley ni das asesoría fiscal.
{ubicacion}
A partir del texto de «{descriptor}», devuelve SOLO un objeto JSON (sin texto
extra) con estas claves, en español, para ayudar a que una persona ENCUENTRE
esta disposición cuando pregunte con palabras coloquiales:

- "denominacion_comun": nombre corto y común del tema (string).
- "temas": 4-10 temas/conceptos que trata (array de strings cortos).
- "terminos_coloquiales": cómo la gente se refiere a esto en lenguaje cotidiano,
  incluyendo búsquedas típicas Y las SIGLAS o acrónimos oficiales conocidos
  (muchos regímenes y figuras fiscales se conocen por sus siglas, p. ej. un
  "Régimen Simplificado de Confianza" se conoce como "RESICO"). Si el tema tiene
  una sigla establecida, INCLÚYELA. La ley usa términos técnicos donde la gente
  usa otra palabra: cuando el texto regule una figura cuyo nombre cotidiano es
  distinto, incluye SIEMPRE la palabra cotidiana — p. ej. "factura" si el texto
  dice "comprobante fiscal" o "CFDI"; "gasolina" si dice "combustibles";
  "aguinaldo" si dice "gratificaciones"; "e.firma" si dice "certificado de firma
  electrónica avanzada"; "comprar un coche/auto" si dice "inversiones en
  automóviles" (array de strings).
- "resumen": 1-3 oraciones en lenguaje llano de lo que establece (string).
- "preguntas_ejemplo": 3-6 preguntas reales que esta disposición respondería
  (array de strings).

Reglas estrictas:
- Apégate al contenido del texto; no inventes obligaciones que no aparezcan.
- Usa la ubicación (sección/capítulo) para nombrar bien el régimen o tema e
  incluir sus términos coloquiales y siglas; no infieras de tu memoria un régimen
  que el texto o la ubicación no indiquen.
- No cites fechas ni números de reforma.
- Todas las claves de lista deben ser arreglos de strings, nunca null. Si el
  texto es muy corto o está derogado, devuelve igual arreglos (pueden tener
  pocos elementos) usando el tema o número del artículo.
- Devuelve únicamente el JSON.

Texto:
\"\"\"
{plain_text}
\"\"\""""


def _extract_json(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw.strip(), re.DOTALL)
    if not m:
        raise ValueError("la respuesta del LLM no contiene JSON")
    return json.loads(m.group(0))


def _clean_list(v) -> list[str]:
    """Coerce la salida del LLM a una lista de strings limpios (tolerante).

    El modelo a veces devuelve un string suelto, números, o entradas vacías
    para artículos cortos/derogados. En vez de tirar todo el registro,
    normalizamos: string→[string], se descartan no-strings/vacíos, se hace strip.
    """
    if isinstance(v, str):
        v = [v]
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        if isinstance(x, str) and x.strip():
            out.append(x.strip())
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            out.append(str(x))
    return out


def _normalize(data: dict) -> dict:
    """Limpia in-place las listas y los textos antes de validar/ensamblar."""
    for k in CAMPOS_LISTA:
        data[k] = _clean_list(data.get(k))
    for k in CAMPOS_TEXTO:
        if isinstance(data.get(k), str):
            data[k] = data[k].strip()
    return data


def validate(data: dict) -> None:
    """Valida un registro YA normalizado (ver `_normalize`).

    Los campos de texto (la denominación y el resumen) anclan el registro y son
    obligatorios. Las listas de búsqueda pueden quedar vacías individualmente
    (un artículo corto puede no dar 4-10 temas), pero al menos UNA debe tener
    contenido para que el enriquecimiento aporte recall; si no, no vale la pena
    guardarlo (la unidad se indexa por su texto de todas formas).
    """
    for k in CAMPOS_TEXTO:
        if not isinstance(data.get(k), str) or not data[k].strip():
            raise ValueError(f"campo '{k}' debe ser texto no vacío")
    for k in CAMPOS_LISTA:
        v = data.get(k)
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise ValueError(f"campo '{k}' debe ser lista de strings")
    if not any(data.get(k) for k in CAMPOS_LISTA):
        raise ValueError("ninguna lista de búsqueda tiene contenido")


def _hash_de(plain_text: str, contexto: str = "") -> str:
    """Hash de regeneración. Incluye el contexto jerárquico para que la unidad se
    re-enriquezca cuando aparece/cambia su sección (sin contexto, el hash es el de
    antes → la constitución y las unidades sin jerarquía no se invalidan)."""
    return text_hash(f"{plain_text}\n##CTX##\n{contexto}" if contexto else plain_text)


def assemble(unidad, doc: Documento, plain_text: str, data: dict, modelo: str,
             contexto: str = "") -> dict:
    _normalize(data)
    validate(data)
    return {
        "clave": unidad.clave,
        "documento": doc.clave,
        "etiqueta": unidad.etiqueta,
        "_generado": {
            "modelo": modelo, "schema": SCHEMA_VERSION,
            "hash_texto": _hash_de(plain_text, contexto), "advertencia": ADVERTENCIA,
        },
        "denominacion_comun": data["denominacion_comun"],
        "temas": data["temas"],
        "terminos_coloquiales": data["terminos_coloquiales"],
        "resumen": data["resumen"],
        "preguntas_ejemplo": data["preguntas_ejemplo"],
    }


def needs_refresh(unidad, existing: dict | None) -> bool:
    if not existing:
        return True
    actual = _hash_de(texto_plano(unidad), getattr(unidad, "contexto", ""))
    return existing.get("_generado", {}).get("hash_texto") != actual


def enrich_unit(unidad, doc: Documento, call, modelo: str) -> dict:
    plain = texto_plano(unidad)
    contexto = getattr(unidad, "contexto", "")
    descriptor = f"{unidad.etiqueta} ({doc.sigla})"
    data = _extract_json(call(build_prompt(descriptor, plain, contexto)))
    return assemble(unidad, doc, plain, data, modelo, contexto)


# --------------------------------------------------------------------------- #
# Orquestación + integración con las APIs (producción)                        #
# --------------------------------------------------------------------------- #
MANIFEST = """# metadata/<clave>/generado/ — contenido GENERADO por IA (no canónico)

⚠️  Estos archivos los produce un LLM y sirven SOLO para mejorar la búsqueda
(recall) cuando alguien pregunta con lenguaje coloquial. **No son texto oficial
ni fuente de cita.** La verdad está en el `.md` de la unidad; las citas, en
`pasajes.jsonl`. Se regenera por hash solo cuando el texto cambia.
"""


def anthropic_caller(model: str):
    """`call(prompt)->str` con la API de Anthropic (ANTHROPIC_API_KEY)."""
    import anthropic                                    # import perezoso
    client = anthropic.Anthropic()

    def call(prompt: str) -> str:
        msg = client.messages.create(
            model=model, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return call


def openai_caller(model: str):
    """`call(prompt)->str` con la API de OpenAI (OPENAI_API_KEY)."""
    from openai import OpenAI                           # import perezoso
    client = OpenAI()

    def call(prompt: str) -> str:
        resp = client.chat.completions.create(
            model=model, max_tokens=1500,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    return call


def caller_for(proveedor: str, model: str):
    if proveedor == "anthropic":
        return anthropic_caller(model)
    if proveedor == "openai":
        return openai_caller(model)
    raise ValueError(f"proveedor desconocido: {proveedor!r} (usa 'anthropic' u 'openai')")


def run_enrichment(unidades, doc: Documento, data_repo, call, modelo: str,
                   force: bool = False, reintentos: int = 2,
                   progreso_cada: int = 25) -> dict:
    """Genera/actualiza el enriquecimiento de las unidades que lo necesitan.

    Best-effort: si el LLM devuelve algo inválido, reintenta y, si aún falla,
    SALTA esa unidad sin abortar (esta capa nunca es crítica). Caché por hash.
    Cada `progreso_cada` unidades procesadas (no cacheadas) imprime el avance
    con flush: un documento grande (la RMF son ~1,200 reglas) tarda decenas de
    minutos y sin esto el log de CI queda mudo hasta el final del documento.
    """
    gen_dir = Path(data_repo) / "metadata" / doc.clave / "generado"
    gen_dir.mkdir(parents=True, exist_ok=True)
    (gen_dir / "README.md").write_text(MANIFEST, encoding="utf-8")

    generados = omitidos = fallidos = 0
    errores: list[str] = []
    total = len(unidades)
    for i, u in enumerate(unidades, 1):
        path = gen_dir / f"{u.clave}.json"
        existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
        if not force and not needs_refresh(u, existing):
            omitidos += 1
            continue
        record, ultimo = None, None
        for _ in range(max(1, reintentos)):
            try:
                record = enrich_unit(u, doc, call, modelo); break
            except Exception as e:                       # LLM no-determinista: reintenta
                ultimo = e
        if record is None:
            fallidos += 1; errores.append(f"{doc.clave}/{u.clave}: {ultimo}")
        else:
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            generados += 1
        if progreso_cada and (generados + fallidos) % progreso_cada == 0:
            print(f"  {doc.clave}: {i}/{total} unidades "
                  f"(generados={generados} fallidos={fallidos})", flush=True)
    return {"generados": generados, "omitidos": omitidos,
            "fallidos": fallidos, "errores": errores}
