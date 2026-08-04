def detect_id_type(id_str):
    """
    Identifica el tipo de ID.
    """
    if not id_str: 
        return None
    
    id_str = id_str.strip().upper()
    
    if id_str.startswith(("PRJN", "PRJE", "PRJD")): 
        return "bioproject"
    if id_str.startswith(("SRP", "ERP", "DRP")): 
        return "study"
    if id_str.startswith(("SRX", "ERX", "DRX")): 
        return "experiment"
    if id_str.startswith(("SAMN")): 
        return "biosample"
    if id_str.startswith(("SRS", "ERS", "DRS")):
        return "sample"
    if id_str.startswith(("SRR", "ERR", "DRR")): 
        return "run"
    
    if id_str.startswith(("GSM")): 
        return "geo_sample"
    if id_str.startswith("GSE"): 
        return "geo_series"
    if id_str.startswith("GPL"): 
        return "geo_platform"
    return None