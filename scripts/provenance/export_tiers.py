#!/usr/bin/env python3
"""
Tier 1/2/3 AMG adaylarını habitat bilgisiyle ayrı temiz dosyalara çıkar.
Yapısal validasyon (Adım 5) için hazırlık.
"""
import pandas as pd
from pathlib import Path

OUT  = Path("/home/yazganuur/projects/verm/sonuclar/faz_c_v2")
AMG  = OUT / "amg_final_catalog.tsv"
BAPS = Path("/home/yazganuur/projects/verm/02_habitat/baps_master_v1.tsv")

print("Yükleniyor...")
amg  = pd.read_csv(AMG, sep="\t", dtype=str, low_memory=False)
baps = pd.read_csv(BAPS, sep="\t", dtype=str)[
    ["baps_id","habitat_broad","habitat_fine","organism","genus"]
].drop_duplicates()

# Habitat join
m = amg.merge(baps, left_on="contig_id", right_on="baps_id", how="left")
print(f"Join sonrası: {len(m):,} satır")

# Tier tanımları
tiers = {
    "tier1": "YÜKSEK_DOĞRULANMIŞ",
    "tier2": "YÜKSEK_BAĞLAMLI",
    "tier3": "YÜKSEK_CONTIG_DESTEKLI",
}

# Önemli sütunlar (yapısal analiz için gerekli olanlar)
keep_cols = [
    "protein_id","contig_id","orf_idx",
    "src_dramv","src_vibrant","src_concordant",
    "dram_ko_id","dram_amg_flags",
    "vibrant_ko_id","kofam_ko_id","kofam_trust_idx",
    "pfam_name","pfam_acc","pfam_score",
    "eggnog_cog","eggnog_kegg_ko",
    "flag_misannotation","flag_virus_specific",
    "ko_vlscore","pfam_vlscore",
    "left_class","right_class","context_score","phrog_support",
    "confidence_final",
    "habitat_broad","habitat_fine","organism","genus",
]
keep_cols = [c for c in keep_cols if c in m.columns]

for tname, label in tiers.items():
    sub = m[m["confidence_final"] == label][keep_cols].copy()
    out_path = OUT / f"{tname}_amg_with_habitat.tsv"
    sub.to_csv(out_path, sep="\t", index=False)
    print(f"\n{tname} ({label}): {len(sub):,} protein → {out_path.name}")
    print(f"  Habitat: {sub['habitat_broad'].value_counts().to_dict()}")
    print(f"  Top Pfam: {sub['pfam_name'].value_counts().head(5).to_dict()}")

# Birleşik PHROG-destekli yüksek set (Tier 1+2+3)
combined = m[m["confidence_final"].isin(tiers.values())][keep_cols].copy()
combined.to_csv(OUT / "tier123_combined_amg.tsv", sep="\t", index=False)
print(f"\nBirleşik (Tier 1+2+3): {len(combined):,} protein → tier123_combined_amg.tsv")

print("\nTamamlandı.")
