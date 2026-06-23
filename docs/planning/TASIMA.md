# TASIMA — VermAMG Git'e Hazırlık & Veri Ayrıştırma Planı

> Amaç: VermAMG'yi İtalyan lab'a gönderilebilecek **tertemiz, profesyonel,
> GitHub-ready** bir repo haline getirmek. Kod git'e gider; devasa veri,
> veritabanı, container ve V1 artefaktları git dışında kalır. Hiçbir bilimsel
> veri silinmez — git'e girmeyenler lokalde/arşivde korunur.

Tarih: 2026-06-22. Bu belge onaylanınca uygulanır; aşağıdaki komutlar hazırdır.

---

## 1. Boyut gerçeği (neden ayrıştırıyoruz)

| Klasör | Boyut | Tür | Karar |
|---|---:|---|---|
| `legacy_examples/` | 17 GB | V1 tarihsel örnekler | ARŞİV (C) |
| `resources/` | 16 GB | DB + container + araçlar | LOKAL, gitignore (B) |
| `results/` | 15 GB | V1 sonuç artefaktları | ARŞİV (C) |
| `incoming/` | 997 MB | Precomputed demo verisi (665) | LOKAL, gitignore (B) |
| `06_visual_qc_v6/` | 868 MB | V1 görsel çıktı | ARŞİV (C) |
| `04_p2rank/` | 658 MB | V1 p2rank çıktı | ARŞİV (C) |
| `01_colabfold/` | 447 MB | V1 colabfold çıktı | ARŞİV (C) |
| `00_inputs_transfer/` | 242 MB | TRUBA transfer paketi | ARŞİV (C) |
| `02_foldseek/` | 24 MB | V1 foldseek çıktı | ARŞİV (C) |
| **Kod** (`scripts/ docs/ config/ run_configs/ run_templates/ pipeline_contracts/`) | **< 5 MB** | Asıl pipeline | **GIT (A)** |

**Sonuç:** Repo ~50 GB; asıl pipeline ~5 MB. İş = kodu veriden ayırmak.

### Neden DB'ler git'e konmuyor (önemli)
- GitHub **dosya başına 100 MB** sınırı koyar; üstü push'ta reddedilir.
- `resources/databases/` 11 GB (foldseek 6.7G + colabfold 3.5G),
  `resources/containers/` 4.7 GB (`.sif` dosyaları 3.9G + 1G). Tek tek bile sınırın
  çok üstünde.
- Git-LFS GitHub ücretsiz katmanı 1 GB/ay — 16 GB için yetersiz ve pahalı.
- **Profesyonel norm:** Ciddi biyoinformatik pipeline'ları DB'yi git'e koymaz;
  bir `setup` scripti ile indirtir/oluşturur. Temiz repo + setup scripti, lab'a
  "bu kişi işini biliyor" izlenimi verir. 16 GB'lık git tam tersi.

---

## 2. Üç katmanlı ayrıştırma

### Katman A — GIT'e gider (kaynak, ~5 MB)
```
scripts/            # tüm pipeline kodu (.bak/.before_*/__pycache__ temizlenmiş)
docs/               # küratörlenmiş dokümanlar (bkz. §5)
run_templates/      # 2 temiz kullanıcı şablonu (local + HPC) + README
run_configs/        # sadece örnek config'ler (küçük)
config/             # env varsayılanları (.bak temizlenmiş)
pipeline_contracts/ # stage IO sözleşmeleri
examples/           # YENİ: minik precomputed smoke verisi (birkaç protein) + config
README.md           # YENİ: profesyonel proje tanıtımı (İngilizce)
LICENSE             # YENİ
.gitignore          # YENİ (bkz. §3)
setup.sh            # YENİ: araç/DB indirme-kurma scripti
requirements.txt    # YENİ: python bağımlılıkları
```

### Katman B — Lokalde kalır, gitignore'lanır (çalışmak için gerekli, ~16 GB)
```
resources/databases/    # foldseek + colabfold DB'leri
resources/containers/    # colabfold + pymol .sif
resources/tools/         # p2rank, foldseek binary (setup.sh bunları getirir)
incoming/                # tam precomputed 665 veri seti (gerçek dataset)
runs/<fullatom_refs_run> # config'in işaret ettiği full-atom referans cache
```
Bunlar senin makinende durur; pipeline burada gerçek çalışır. Git'e girmez.
`setup.sh` yeni bir kullanıcının bunları kurmasını otomatikleştirir.

### Katman C — Arşive taşınır (V1 artefakt, ~48 GB; silinmez, taşınır)
Repo dışında bir arşive (örn. `D:\VermAMG_archive\`) taşınır. Geri alınabilir,
pipeline'dan yeniden üretilebilir.
```
legacy_examples/  results/  00_inputs_transfer/
01_colabfold/  02_foldseek/  04_p2rank/  05_overlay_manifest/  05_reference_panel/
06_residue_level/  06_visual_qc_v6/  07_decision_matrix/  08_rulebook_evidence/
09_regression_pilot32/  10_results_package/  00_inputs/ (örnek dışı kısım)
backups/  tmp/  logs/  work/  results/  exports/  pipeline_state/  run_sets/  smoke_test/
HOXD_sunum*.pptx (sunum — pipeline değil)
```

### Silinecek saf çöp (geri alınmasına gerek yok)
```
"1"  (boş dosya)
**/*.bak  **/*.bak_*  **/*.before_*  **/*~  **/*.orig
**/__pycache__/  **/*.pyc
00_inputs/tier1_missing_ids.txt (boş)
scripts/vermamg_lib/*.before_*_patch  (yedek kod kopyaları)
scripts/tmp_*.sh  (geçici denetim scriptleri — kontrol edilip)
```

---

## 3. `.gitignore` (kök)
```gitignore
# --- Ağır veri / araç / container (lokalde kalır, setup.sh getirir) ---
resources/
incoming/

# --- Run çıktıları (her kullanıcı kendi makinesinde üretir) ---
runs/
work/
results/
exports/
logs/
tmp/
pipeline_state/

# --- V1 artefaktları (arşive taşındı; yine de korunsun) ---
legacy_examples/
00_inputs_transfer/
01_colabfold/
02_foldseek/
04_p2rank/
05_overlay_manifest/
05_reference_panel/
06_residue_level/
06_visual_qc_v6/
07_decision_matrix/
08_rulebook_evidence/
09_regression_pilot32/
10_results_package/
backups/
run_sets/
smoke_test/

# --- Python ---
__pycache__/
*.pyc
*.pyo

# --- Yedek/çöp ---
*.bak
*.bak_*
*.before_*
*~
*.orig

# --- Büyük ikili / sunum ---
*.sif
*.pptx

# --- IDE ---
.vscode/
.idea/

# examples/ açıkça izinli (gitignore'a takılmasın diye gerekirse !examples/)
```
> Not: `examples/` içindeki minik veri git'e GİRER. Eğer örnek veriyi
> `00_inputs/` altından alırsak, ilgili dosyalar için `!` istisnası eklenir.

---

## 4. Smoke demo stratejisi (klonla → çalıştır → gör)

Yeni `examples/smoke_precomputed/`:
- 3–5 proteinin **precomputed** query PDB'leri + ilgili foldseek hit tablolarının
  alt kümesi (incoming/'dan süzülür) → birkaç MB.
- Hazır bir `examples/smoke_precomputed/config.yaml` (precomputed mod).
- `colabfold.mode=precomputed`, `foldseek.mode=precomputed_all_hits` →
  **hiçbir DB/GPU gerekmeden** M06B→M14 tüm downstream çalışır ve pipeline'ın
  vaadettiği tüm çıktıları üretir.

Kullanıcı deneyimi:
```bash
git clone <repo> && cd VermAMG
python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml --resume --follow
# -> exports/ altında final yorum tablosu; 5 dakikada "çalışıyor" kanıtı
```
LIVE mod (FASTA→ColabFold→Foldseek) için kullanıcı `setup.sh` ile DB/araç kurar,
sonra `run_templates/`'tan local ya da HPC şablonunu doldurur.

---

## 5. docs/ küratörü (git'e giden dokümanlar)
Tut: `ARCHITECTURE_V2_PROJECT_RUNS.md`, `STAGE_INPUT_CONTRACTS.md`,
`PIPELINE_MAP.md`, `MODULE_IO_CONTRACTS.tsv`, `RESOURCE_MANIFEST_GUIDE.md`,
`pipeline_contracts/`, `io_contracts/`, `input_schema/`, `file_format_examples/`.

Arşive/güncelle (V1'e özgü veya iç notlar): `README_FOR_VSCODE_AGENT.md`,
`README_Bolum9_Tier1_Master_Pipeline.md`, `RUN_CONFIG_ORCHESTRATION_V1.md`,
`CURRENT_RUNTIME_LAYOUT.md`, `LOCAL_MIRROR_RUNBOOK.md`,
`DO_NOT_EDIT_GENERATED_ARTIFACTS.md`, `LEGACY_EXAMPLES_POLICY.md`,
`VERMAMG_PORTABLE_ARCHITECTURE_DRAFT.md`.

Yeni public doküman seti (İngilizce, lab için):
- `README.md` (kök): ne yapar, mimari özet, quickstart, smoke demo, lisans.
- `docs/INSTALL.md`: setup.sh, DB/araç kurulumu, bağımlılıklar.
- `docs/USAGE.md`: local & HPC şablon doldurma, çalıştırma, çıktı okuma.
- `run_templates/README_RUN_TEMPLATES.md`: 2 şablonun alan-alan açıklaması.

---

## 6. Uygulama adımları (onaylanınca — sıralı, güvenli)

```bash
# 0) Güvenlik: önce arşiv klasörü
mkdir -p /d/VermAMG_archive

# 1) Saf çöpü sil
rm -f "/d/VermAMG/1" "/d/VermAMG/00_inputs/tier1_missing_ids.txt"
find /d/VermAMG -name "__pycache__" -type d -prune -exec rm -rf {} +
find /d/VermAMG -type f \( -name "*.bak" -o -name "*.bak_*" -o -name "*.before_*" \) \
  -not -path "*/legacy_examples/*" -delete   # legacy zaten arşive gidecek

# 2) Örnek veriyi ayır (smoke için birkaç protein) -> examples/
#    (ayrı script ile süzülecek; bkz. §4)

# 3) V1 artefaktlarını arşive TAŞI (silme!)
for d in legacy_examples results 00_inputs_transfer 01_colabfold 02_foldseek \
         04_p2rank 05_overlay_manifest 05_reference_panel 06_residue_level \
         06_visual_qc_v6 07_decision_matrix 08_rulebook_evidence \
         09_regression_pilot32 10_results_package backups run_sets smoke_test \
         work exports pipeline_state logs tmp; do
  [ -e "/d/VermAMG/$d" ] && mv "/d/VermAMG/$d" /d/VermAMG_archive/
done
mv /d/VermAMG/HOXD_sunum*.pptx /d/VermAMG_archive/ 2>/dev/null

# 4) Git scaffolding
cd /d/VermAMG
# .gitignore, README.md, LICENSE, setup.sh, requirements.txt yazılır (ayrı adım)

# 5) Doğrula: smoke demo çalışıyor mu (DB'siz)
python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml --resume --follow

# 6) git init + ilk commit
git init && git add -A && git status   # boyut kontrolü; <50MB beklenir
```

> Her adımdan sonra durulur ve doğrulanır. `runs/<fullatom_refs_run>` ve
> `incoming/` LOKALDE kalır (gitignore) — precomputed örneğin tam 665 versiyonu
> hâlâ çalışsın diye. Sadece smoke örneği git'e girer.

---

## 7. Açık karar (senin onayın gerekiyor)
- **DB'leri git'e koyma** isteğini, GitHub 100 MB sınırı nedeniyle uygulanamaz
  buldum; yerine "kod git'te + setup.sh + minik smoke" yolunu öneriyorum (§1, §4).
  Bunu onaylıyor musun, yoksa Git-LFS/harici host gibi bir alternatif mi
  istersin? (Önerim: setup.sh yolu — en temiz ve profesyonel.)
- Arşiv konumu `D:\VermAMG_archive\` uygun mu?
