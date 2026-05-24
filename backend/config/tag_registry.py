"""
Tag Registry — maps human aliases → exact AVEVA Historian TagNames.
Built from the 8 real CSV files.

TagName pattern:  {System}.{Asset}   (dot-separated)
  MRS_Access_Control.AccessChannels_QR
  MRS_Access_Control.Beaches_Vip
  MRS_Access_Control.MainGate_Vip
  MRS_CCTV.cameras_total_number
  MRS_CCTV.Total_disabled_cameras
  MRS_CCTV.Total_enabled_cameras
  MRS_Gate_APIs.Gates.Fail
  MRS_Gate_APIs.Gates.Success
"""

TAG_REGISTRY: dict[str, str] = {
    # ── Access Control ──────────────────────────────────────────
    "accesschannels_qr":           "MRS_Access_Control.AccessChannels_QR",
    "access channels qr":          "MRS_Access_Control.AccessChannels_QR",
    "qr access":                   "MRS_Access_Control.AccessChannels_QR",
    "qr channels":                 "MRS_Access_Control.AccessChannels_QR",
    "qr":                          "MRS_Access_Control.AccessChannels_QR",
    "access channels":             "MRS_Access_Control.AccessChannels_QR",

    "beaches_vip":                 "MRS_Access_Control.Beaches_Vip",
    "beaches vip":                 "MRS_Access_Control.Beaches_Vip",
    "beach vip":                   "MRS_Access_Control.Beaches_Vip",
    "beaches vip access":          "MRS_Access_Control.Beaches_Vip",
    "vip beach":                   "MRS_Access_Control.Beaches_Vip",
    "beaches vip access point":    "MRS_Access_Control.Beaches_Vip",
    "beach":                       "MRS_Access_Control.Beaches_Vip",
    "beaches":                     "MRS_Access_Control.Beaches_Vip",

    "maingate_vip":                "MRS_Access_Control.MainGate_Vip",
    "main gate vip":               "MRS_Access_Control.MainGate_Vip",
    "main gate":                   "MRS_Access_Control.MainGate_Vip",
    "maingate":                    "MRS_Access_Control.MainGate_Vip",
    "vip main gate":               "MRS_Access_Control.MainGate_Vip",
    "main gate vip access point":  "MRS_Access_Control.MainGate_Vip",

    # ── CCTV ────────────────────────────────────────────────────
    "cameras_total_number":        "MRS_CCTV.cameras_total_number",
    "total cameras":               "MRS_CCTV.cameras_total_number",
    "camera count":                "MRS_CCTV.cameras_total_number",
    "number of cameras":           "MRS_CCTV.cameras_total_number",
    "all cameras":                 "MRS_CCTV.cameras_total_number",
    "cctv total":                  "MRS_CCTV.cameras_total_number",
    "how many cameras":            "MRS_CCTV.cameras_total_number",

    "total_disabled_cameras":      "MRS_CCTV.Total_disabled_cameras",
    "disabled cameras":            "MRS_CCTV.Total_disabled_cameras",
    "cameras disabled":            "MRS_CCTV.Total_disabled_cameras",
    "offline cameras":             "MRS_CCTV.Total_disabled_cameras",
    "down cameras":                "MRS_CCTV.Total_disabled_cameras",
    "cameras down":                "MRS_CCTV.Total_disabled_cameras",
    "cameras offline":             "MRS_CCTV.Total_disabled_cameras",

    "total_enabled_cameras":       "MRS_CCTV.Total_enabled_cameras",
    "enabled cameras":             "MRS_CCTV.Total_enabled_cameras",
    "cameras enabled":             "MRS_CCTV.Total_enabled_cameras",
    "active cameras":              "MRS_CCTV.Total_enabled_cameras",
    "online cameras":              "MRS_CCTV.Total_enabled_cameras",
    "working cameras":             "MRS_CCTV.Total_enabled_cameras",
    "cameras online":              "MRS_CCTV.Total_enabled_cameras",
    "cameras active":              "MRS_CCTV.Total_enabled_cameras",

    # ── Gate APIs ────────────────────────────────────────────────
    "gates_fail":                  "MRS_Gate_APIs.Gates.Fail",
    "gates fail":                  "MRS_Gate_APIs.Gates.Fail",
    "gate failures":               "MRS_Gate_APIs.Gates.Fail",
    "failed gates":                "MRS_Gate_APIs.Gates.Fail",
    "gate errors":                 "MRS_Gate_APIs.Gates.Fail",
    "api failures":                "MRS_Gate_APIs.Gates.Fail",
    "gate fail":                   "MRS_Gate_APIs.Gates.Fail",
    "failures":                    "MRS_Gate_APIs.Gates.Fail",

    "gates_success":               "MRS_Gate_APIs.Gates.Success",
    "gates success":               "MRS_Gate_APIs.Gates.Success",
    "gate success":                "MRS_Gate_APIs.Gates.Success",
    "successful gates":            "MRS_Gate_APIs.Gates.Success",
    "gates passing":               "MRS_Gate_APIs.Gates.Success",
    "api success":                 "MRS_Gate_APIs.Gates.Success",
    "gate successes":              "MRS_Gate_APIs.Gates.Success",
}

# Reverse map: TagName → canonical human label (for answer formatting)
TAG_LABELS: dict[str, str] = {
    "MRS_Access_Control.AccessChannels_QR":  "Access Channels (QR)",
    "MRS_Access_Control.Beaches_Vip":        "Beaches VIP Access Point",
    "MRS_Access_Control.MainGate_Vip":       "Main Gate VIP Access Point",
    "MRS_CCTV.cameras_total_number":         "Total CCTV Cameras",
    "MRS_CCTV.Total_disabled_cameras":       "Disabled CCTV Cameras",
    "MRS_CCTV.Total_enabled_cameras":        "Enabled CCTV Cameras",
    "MRS_Gate_APIs.Gates.Fail":              "Gate API Failures",
    "MRS_Gate_APIs.Gates.Success":           "Gate API Successes",
}

# Domain map: TagName → domain (for multi-tag queries)
TAG_DOMAIN: dict[str, str] = {
    "MRS_Access_Control.AccessChannels_QR":  "access_control",
    "MRS_Access_Control.Beaches_Vip":        "access_control",
    "MRS_Access_Control.MainGate_Vip":       "access_control",
    "MRS_CCTV.cameras_total_number":         "cctv",
    "MRS_CCTV.Total_disabled_cameras":       "cctv",
    "MRS_CCTV.Total_enabled_cameras":        "cctv",
    "MRS_Gate_APIs.Gates.Fail":              "gate_apis",
    "MRS_Gate_APIs.Gates.Success":           "gate_apis",
}

ALL_TAG_NAMES = list(TAG_LABELS.keys())
