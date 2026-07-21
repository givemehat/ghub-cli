"""
Cliente HTTP delgado sobre la API de genomic-hub.

Centraliza las rutas y el manejo de errores para que cli.py solo se
preocupe de la interacción con el usuario.
"""
from pathlib import Path
from typing import List, Optional

import requests


class APIError(Exception):
    """Error de la API, ya sea error de sistema (4xx/5xx) o de operación (200 con status=error)."""

    def __init__(self, status_code: int, detail: str, code: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


class GenomicHubClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    # ---------- internals ----------
    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/ncbi-mirror{path}"

    def _handle_response(self, resp: requests.Response) -> dict:
        try:
            data = resp.json()
        except ValueError:
            raise APIError(resp.status_code, resp.text or "Respuesta vacía o no-JSON.")

        if not resp.ok:
            # Error de sistema: {status, detail, code}
            raise APIError(resp.status_code, data.get("detail", "Error desconocido."), data.get("code", ""))

        if isinstance(data, dict) and data.get("status") == "error":
            # Error de operación con HTTP 200: {status, detail, code, ...}
            raise APIError(resp.status_code, data.get("detail", "Error desconocido."), data.get("code", ""))

        return data

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            return self.session.request(method, self._url(path), timeout=self.timeout, **kwargs)
        except requests.exceptions.ConnectionError:
            raise APIError(0, f"No se pudo conectar a {self.base_url}. ¿Está corriendo el servidor?")
        except requests.exceptions.Timeout:
            raise APIError(0, f"Timeout tras {self.timeout}s esperando respuesta de {self.base_url}.")
        except requests.exceptions.RequestException as e:
            raise APIError(0, f"Error de red: {e}")

    def _get(self, path: str, params: dict = None) -> dict:
        resp = self._request("GET", path, params=params)
        return self._handle_response(resp)

    def _post(self, path: str, json_body: dict = None) -> dict:
        resp = self._request("POST", path, json=json_body)
        return self._handle_response(resp)

    # ---------- queries & sync ----------
    def check_bulk(self, ids: List[str]) -> dict:
        return self._post("/check-bulk", {"ids": ids})
        
    def sync(self, ids: List[str]) -> dict:
        """
        Detecta si es 1 o varios IDs para usar el endpoint adecuado.
        También corrige el error 422 enviando la llave correcta 'ids' en el bulk.
        """
        if len(ids) == 1:
            # Endpoint individual: POST /sync/{project_id} (no requiere body)
            return self._post(f"/sync/{ids[0]}")
        else:
            # Endpoint masivo: POST /sync-bulk (requiere body con 'ids')
            return self._post("/sync-bulk", {"ids": ids})

    def explore(self, query: str, page: int = 1, page_size: int = 20) -> dict:
        return self._get("/explore", {"query": query, "page": page, "page_size": page_size})

    def task_status(self, task_id: str) -> dict:
        return self._get(f"/task/{task_id}")
    
# ---------- batch jerárquicos ----------
    def get_bioprojects_batch(self, ids: List[str], page: int = 1, page_size: int = 20, mask: dict = None) -> dict:
        payload = {"ids": ids, "page": page, "page_size": page_size}
        if mask: payload["mask"] = mask
        # ANTES: "/bioprojects/experiments" -> AHORA: "/bioprojects"
        return self._post("/bioprojects", payload)

    def get_experiments_batch(self, ids: List[str], page: int = 1, page_size: int = 20, mask: dict = None) -> dict:
        payload = {"ids": ids, "page": page, "page_size": page_size}
        if mask: payload["mask"] = mask
        # ANTES: "/experiments/runs" -> AHORA: "/experiments"
        return self._post("/experiments", payload)

    def get_samples_batch(self, ids: List[str], mask: dict = None) -> dict:
        payload = {"ids": ids}
        if mask: payload["mask"] = mask
        # ANTES: "/samples/details" -> AHORA: "/samples"
        return self._post("/samples", payload)

    def get_runs_batch(self, ids: List[str], mask: dict = None) -> dict:
        payload = {"ids": ids}
        if mask: payload["mask"] = mask
        # ANTES: "/runs/details" -> AHORA: "/runs"
        return self._post("/runs", payload)

    def export_full_branch(self, target_id: str, mask: dict = None) -> dict:
        return self._post(f"/export/full-branch/{target_id}", mask or {})

    # ---------- downloads ----------
    def request_download(self, run_id: str, email: str) -> dict:
        return self._post(f"/download/request/{run_id}", {"email": email})
    
    def verify_otp(self, request_id: int, email: str, otp_code: str) -> dict:
        return self._post(f"/download/verify/{request_id}", {"email": email, "otp_code": otp_code})

    def download_file(self, run_id: str, email: str, output_path: Optional[str] = None) -> str:
        resp = self._request("GET", f"/download/file/{run_id}", params={"email": email}, stream=True)

        if not resp.ok:
            try:
                data = resp.json()
                raise APIError(resp.status_code, data.get("detail", "Error desconocido."), data.get("code", ""))
            except ValueError:
                raise APIError(resp.status_code, resp.text or "Error desconocido al descargar.")

        # Determinar nombre de archivo
        if output_path:
            dest = Path(output_path)
        else:
            cd = resp.headers.get("Content-Disposition", "")
            filename = run_id + ".tar.gz"
            if "filename=" in cd:
                filename = cd.split("filename=")[-1].strip('"')
            dest = Path.cwd() / filename

        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        return str(dest)
    
    def file_status(self, run_id: str) -> dict:
        return self._get(f"/download/file-status/{run_id}")