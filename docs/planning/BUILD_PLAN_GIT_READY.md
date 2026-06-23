# VermAMG — Git-Ready Kusursuz Mimari: 10 Adımlık Uygulama Planı

> **Amaç:** Sabah Codex'in adım adım uygulayacağı, sonunda VermAMG'yi İtalyan
> lab'a gönderilebilecek **tertemiz, profesyonel, GitHub-ready** bir pipeline'a
> dönüştüren plan. Hedef son durum: yeni bir kullanıcı **yalnızca 3 şey** yapar
> ve her şey akar.
>
> **Hedef kullanıcı deneyimi (3 adım):**
> 1. `git clone <repo> VermAMG && cd VermAMG`
> 2. `bash setup.sh` → tüm DB/araç/container/python bağımlılıkları **bilinen
>    yerlere** iner (resources/ altına; her yol bellidir).
> 3. Bir şablonu kopyala, `[FILL]` alanlarını doldur, `python scripts/vermamg.py
>    run --config ...` → FASTA'dan başlayıp pipeline'ın tüm vaadettiği çıktılara.

Tarih: 2026-06-22. Yazan: Claude (Opus 4.8). Uygulayacak: Codex.
Kapsam kararı: **Temizlik + cila** (derin paket restructure HARİÇ — o ayrı gün,
bkz. [RESTRUCTURE_REPORT.md](RESTRUCTURE_REPORT.md)). Veri ayrıştırma temeli:
[TASIMA.md](TASIMA.md).

---

## 0. Bağlam: bilinmesi gerekenler (Codex okumadan başlamasın)

- **Sayı-agnostik kuralı (KRİTİK):** Pipeline hiçbir sabit protein sayısına bağlı
  olmamalı. Kullanıcı 5 de verse 150.000 de verse çalışmalı. Shipped hiçbir
  dosyada `665`/`strict_query_n`/`expected_query_count` gibi sabit OLMAMALI.
- **İki mod, tek downstream:** `colabfold.mode` ∈ {precomputed, live},
  `foldseek.mode` ∈ {precomputed_all_hits, live}. Downstream (M06B→M14) ikisini
  ayırt etmez. Live adapter'lar (`00d_run_colabfold.py`, `00e_run_foldseek.py`)
  zaten kurulu (Paket3 DONE).
- **V2 launcher:** `scripts/vermamg.py` (plan/run/status/stage-info). Şema:
  `schema_version: 2` (örnek: `run_configs/example_project_precomputed_v2.yaml`).
- **Boyut gerçeği:** Repo ~50GB; asıl kod ~5MB (gerçekte scripts/ tracked 1.2MB).
  resources/ 16GB (DB+container+araç), incoming/ 997MB, legacy/results ~32GB.
- **R YOK:** Pipeline saf Python (PyYAML + pandas, Python ≥3.10). Harici araçlar:
  Foldseek, P2Rank(+Java), ColabFold(live, GPU container), PyMOL/ChimeraX(görsel,
  opsiyonel container). DeepTMHMM gelecek eksen, varsayılan kapalı.
- **Zaten yapılmış git scaffolding (bu plan üstüne kuruyor):** `.gitignore`,
  kök `README.md` (revize edilecek), `LICENSE`, `setup.sh` (genişletilecek),
  `requirements.txt`, `docs/DEV_NOTES.md`.
- **BİLİNEN DEFECT (bu plan düzeltecek):** `run_templates/local_wsl_run.yaml.template`
  ve `hpc_slurm_run.yaml.template` **V1 şeması** (`candidate_fasta`, `mode: test`,
  `strict_query_n: 665`) → `vermamg.py` ile ÇALIŞMAZ. README bunlara yönlendiriyor.

---

## 1. Adım — Güvenlik, dal, çöp temizliği (lossless)

**Hedef:** Geri alınamaz iş yapmadan zemini temizle.

**Eylemler:**
- `git init` (henüz değilse), `main`'den `chore/git-ready` dalı aç.
- Repo dışı arşiv: `mkdir -p /d/VermAMG_archive`.
- Saf çöpü sil (geri alınmasına gerek yok):
  - `/d/VermAMG/1`, `00_inputs/tier1_missing_ids.txt` (boş)
  - tüm `*.bak`, `*.bak_*`, `*.before_*`, `*~`, `*.orig` (legacy_examples hariç —
    o zaten arşive gidecek)
  - tüm `__pycache__/`, `*.pyc`
  - `scripts/tmp_*.sh` (geçici denetim scriptleri — `grep` ile kullanılmadığı
    doğrulanırsa)

**Kabul:** `find` ile `.bak/.before_/__pycache__` sayısı 0 (shipped alanlarda);
çekirdek kod (`scripts/vermamg_lib`, `scripts/modules/*.py`) dokunulmamış.

---

## 2. Adım — V1 artefaktlarını arşive taşı (silme değil)

**Hedef:** Kök dizini görsel olarak tertemiz yap; veriyi koru.

**Eylemler (TASIMA.md §6):** Şunları `/d/VermAMG_archive/`'a **taşı** (`mv`):
`legacy_examples/ results/ 00_inputs_transfer/ 01_colabfold/ 02_foldseek/`
`04_p2rank/ 05_overlay_manifest/ 05_reference_panel/ 06_residue_level/`
`06_visual_qc_v6/ 07_decision_matrix/ 08_rulebook_evidence/ 09_regression_pilot32/`
`10_results_package/ backups/ run_sets/ smoke_test/ work/ exports/ pipeline_state/`
`logs/ tmp/ HOXD_sunum*.pptx presentation_assets/`

**LOKALDE kalır (gitignored, taşınmaz — pipeline gerçek çalışsın diye):**
`resources/`, `incoming/`, `runs/` (özellikle `runs/tier1_tier2_colabfold_postrun_fresh_v1_fullatom_refs_v1`).

**Kabul:** Kökte yalnız şunlar görünür: `scripts/ docs/ config/ run_templates/`
`run_configs/ pipeline_contracts/ examples/ resources/ incoming/ runs/ inputs/`
`README.md LICENSE setup.sh requirements.txt .gitignore`. Arşive taşınanların
tümü `.gitignore`'da (zaten var) → git'e girmez.

---

## 3. Adım — İki kusursuz V2 şablonu (local + HPC)

**Hedef:** README'nin "kopyala-doldur-çalıştır" sözünü gerçek kılan, `vermamg.py`
ile ÇALIŞAN, sayı-agnostik şablonlar.

**Eylemler:**
- `run_templates/local_run.yaml.template` (YENİ) — `schema_version: 2`,
  `environment.backend: local`, precomputed + live mod anahtarları, `[FILL]`
  işaretli zorunlu alanlar, bol açıklama.
- `run_templates/hpc_slurm_run_v2.yaml.template` (YENİ) — aynı şema,
  `environment.backend: slurm`, `slurm.*` blok (`account/partition/...` `[FILL]`).
- Her ikisi de hem `colabfold.mode: precomputed|live` hem `foldseek.mode` örnekleri
  içersin; live için `resources.foldseek_bin/pdb_foldseek_db/afsp_foldseek_db` ve
  ColabFold ayarları.
- **HİÇBİR sabit sayı yok** (665 yasak). Şablonlar `inputs.fasta`'yı kullanır.
- V1 şablonlarını arşive taşı: `local_wsl_run.yaml.template`,
  `hpc_slurm_run.yaml.template`, `precomputed_full_run.yaml.template`.
- `precomputed_project_run_v2.yaml.template`'i koru (referans) veya `local_run`'a
  konsolide et.

**Kabul:** `cp run_templates/local_run.yaml.template run_configs/t.yaml` sonrası
`python scripts/vermamg.py plan --config run_configs/t.yaml` → `validation_status
PASS` (örnek/smoke girdilerle). `grep -rn 665 run_templates/` → boş.

---

## 4. Adım — Gömülü smoke örneği (DB'siz, uçtan uca akar)

**Hedef:** Klonlayan kişi **setup.sh çalıştırmadan, DB/GPU olmadan** pipeline'ın
tüm downstream'ini çalıştırıp tüm çıktıları görsün. "Çalışıyor" kanıtı.

**Eylemler:**
- `examples/smoke_precomputed/` oluştur:
  - `data/fasta/` — 3–5 protein FASTA (örn. tier1'den alt küme).
  - `data/query_pdbs/` — bu proteinlerin precomputed query PDB'leri (incoming/'dan
    süzülür; birkaç MB).
  - `data/foldseek/` — bu proteinlere ait `*_vs_pdb/afsp_all_hits.tsv` alt kümesi +
    `collector_manifest.tsv` + `id_map`.
  - `config.yaml` — `schema_version: 2`, precomputed mod, bu küçük girdilere işaret eder.
- **Referans materyalizasyonu kısıtı (Codex DİKKAT):** M09 reference P2Rank,
  `reference_materialization` ister. 16GB cache'e bağımlı olmamak için:
  - **Tercih (a):** Smoke'u M08'e kadar çalıştır → seçilen referansları gör →
    o spesifik full-atom referans dosyalarını (`runs/...fullatom_refs.../`'dan)
    `examples/smoke_precomputed/data/references/`'a kopyala (birkaç düzine küçük
    PDB, hedef < ~20MB) → smoke config `method: full_atom_cache,
    source_run_root: examples/smoke_precomputed/data/references_run` gibi gömülü
    kaynağı kullansın → smoke M14'e ulaşsın.
  - **Yedek (b):** Eğer (a) çok büyürse, smoke'u `--stop-after 060_m08_reference_panel`
    ile sınırla; README'de "tam downstream için DB kurun" notu. (a) hedef, (b) kabul.
- Bundled referans boyutunu ölç; `examples/` toplamı **< 25MB** kalmalı.
- `.gitignore`'a `!examples/` istisnasını ekle (examples git'e GİRER).

**Kabul:** Temiz klonda (setup.sh OLMADAN)
`python scripts/vermamg.py run --config examples/smoke_precomputed/config.yaml
--resume --follow` → hedef (a)'da `320_interpretation_ready_export`'a kadar PASS;
`exports/` altında final tablo üretilir. `du -sh examples/` < 25MB.

---

## 5. Adım — setup.sh: tek komutla tam otomatik kurulum

**Hedef:** Kullanıcının 2. adımı: tek komut, her şey bilinen yerlere.

**Eylemler (mevcut setup.sh genişletilir):**
- Python deps: `pip install -r requirements.txt`.
- Foldseek binary → `resources/tools/foldseek/`.
- Foldseek DB'leri → `resources/databases/foldseek/{pdb,alphafold_swissprot}`
  (`foldseek databases ...`).
- P2Rank → `resources/tools/p2rank/` (release indir/aç) + `java -version` kontrolü.
- ColabFold MSA DB → `resources/databases/colabfold/colabfold_data` (resmi script).
- Container'lar → `resources/containers/` (colabfold `.sif`, pymol `.sif`) —
  apptainer/singularity ile pull veya resmi kaynaktan indir.
- Tek komut hepsini yapar (kullanıcı kararı: "her şey tek komutla"). Yine de
  `--tools-only` / `--skip-containers` bayrakları kalsın (kullanışlılık), ama
  varsayılan = tümü.
- İdempotent (var olanı atla), her bileşeni doğrula, **sonunda config'e
  yapıştırılacak tam yolları yazdır.**
- Linux/WSL kontrolü; Windows'ta WSL yönlendirmesi.

**Kabul:** `bash setup.sh` temiz makinede hatasız çalışır mantığı (gerçek indirme
test edilemese de) `bash -n` PASS; betik her hedef yolu ve config anahtarını basar.

---

## 6. Adım — INSTALL.md / DATABASES.md: "ne, nereden, nereye"

**Hedef:** Kullanıcının istediği "DB'leri nereden/nereye indireceği belli" dosyası.

**Eylemler:** `docs/INSTALL.md` oluştur — her harici bağımlılık için tablo:
| Bileşen | Ne için | Resmi kaynak/URL | Hedef yol (resources/...) | Boyut | Config anahtarı |
- Foldseek (binary + PDB DB + AFSP DB), P2Rank (+Java), ColabFold (DB + container),
  PyMOL container, Python deps. Her satırda **tam indirme komutu** ve **tam hedef
  yol** ve **hangi config alanına yazılacağı**.
- `setup.sh`'in bunları otomatik yaptığını, manuel kurmak isteyen için adımları da
  içerdiğini belirt.
- Disk gereksinimi özeti (~20GB DB/container) + minimum (sadece smoke: 0 DB).

**Kabul:** Her DB/araç için kaynak URL + hedef yol + config anahtarı eksiksiz;
`setup.sh`'teki yollarla **birebir tutarlı**.

---

## 7. Adım — Kök README.md: 3 adımlık deneyime göre yeniden yaz

**Hedef:** Tek bakışta "ne, neden, nasıl" — ve 3 adım net.

**Eylemler:**
- "Quickstart (5 dk, DB'siz)": klonla → `vermamg.py run --config
  examples/smoke_precomputed/config.yaml` → çıktıyı gör. (setup gerektirmez.)
- "Full usage (3 adım)": clone → `setup.sh` → şablon doldur + run.
- V1 şablon referanslarını YENİ V2 şablonlarıyla değiştir (defect düzeltme).
- `docs/INSTALL.md`, `run_templates/README_RUN_TEMPLATES.md`, mimari linkleri.
- İngilizce, profesyonel, sayı-agnostik vurgusu, mod tablosu, roadmap, lisans,
  contact placeholder (kullanıcı adını ekleyecek — README'de açık NOT).

**Kabul:** README'deki her komut ve her dosya linki gerçek ve çalışır; V1 şablon
adı geçmez; `examples/` quickstart'ı gerçekten çalışır (Adım 4 ile tutarlı).

---

## 8. Adım — README_RUN_TEMPLATES.md: İngilizce, V2-only, alan-alan

**Hedef:** Şablon doldurma rehberi kusursuz.

**Eylemler:** `run_templates/README_RUN_TEMPLATES.md`'yi tamamen yeniden yaz:
- Sadece İngilizce (karışık dil giderilir).
- Sadece 2 V2 şablonu anlatır (local + HPC); V1/legacy bahsi kaldırılır.
- Her `[FILL]` alanı için: ne, zorunlu mu, örnek değer, nereden gelir.
- precomputed vs live mod nasıl seçilir; local vs slurm farkı.

**Kabul:** Belge yalnız V2 şablonlarına atıf yapar; `candidate_fasta`/`mode: test`/
`run_label:` gibi V1 terimleri geçmez.

---

## 9. Adım — Doküman küratörü + tutarlılık taraması

**Hedef:** docs/ yalnız güncel V2 dokümanı içersin; hiçbir kırık/eski atıf kalmasın.

**Eylemler:**
- V1'e özgü/iç dokümanları `docs/DEV_NOTES.md`'ye konsolide et veya arşive taşı:
  `README_FOR_VSCODE_AGENT.md`, `README_Bolum9_Tier1_Master_Pipeline.md`,
  `RUN_CONFIG_ORCHESTRATION_V1.md`, `CURRENT_RUNTIME_LAYOUT.md`,
  `LOCAL_MIRROR_RUNBOOK.md`, `LEGACY_EXAMPLES_POLICY.md`,
  `VERMAMG_PORTABLE_ARCHITECTURE_DRAFT.md`.
- Tut + güncelle: `ARCHITECTURE_V2_PROJECT_RUNS.md`, `STAGE_INPUT_CONTRACTS.md`,
  `PIPELINE_MAP.md`, `MODULE_IO_CONTRACTS.tsv`, `RESOURCE_MANIFEST_GUIDE.md`,
  `INSTALL.md`, `DEV_NOTES.md`, `planning/`.
- Global taramalar (shipped alanlarda):
  - `grep -rn "665\|strict_query_n\|expected_query_count"` → yalnız DEV_NOTES'ta
    tarihsel bağlamda olabilir; şablon/kod/README'de OLMAMALI.
  - `grep -rn "candidate_fasta\|run_tier1_master_pipeline"` → README/şablonlarda yok.
  - Tüm README iç linkleri çözülür (kırık link yok).

**Kabul:** Tarama çıktıları temiz; her doküman linki geçerli.

---

## 10. Adım — Doğrulama kapısı + git init + ilk commit

**Hedef:** Push öncesi kusursuzluk kanıtı.

**Eylemler — Kabul Matrisi (hepsi PASS olmalı):**
1. `python -m py_compile` tüm `scripts/**/*.py` → PASS.
2. `vermamg.py plan` precomputed örnek config → `validation_status PASS`.
3. `vermamg.py plan` live örnek config → `validation_status PASS`.
4. Smoke: `vermamg.py run --config examples/smoke_precomputed/config.yaml --resume`
   → hedef (a) M14'e PASS (veya yedek (b) M08'e PASS).
5. `validate-stage 020/030` (live) → kontrat doğru.
6. `git status` + `git add -A --dry-run`: tracked boyut **< 5MB**; hiçbir
   `resources/ incoming/ runs/ *.sif` izlenmez.
7. Taramalar (Adım 9) temiz.
8. README quickstart komutları elle bir kez koşulur.
- Sonra `git add -A && git commit -m "VermAMG: git-ready clean architecture"`.
- `git status` ile son boyut/tracked dosya listesi raporlanır.

**Kabul:** Tüm 8 madde PASS; commit edilen ağaç yalnız kod+doküman+şablon+smoke
(~2–5MB).

---

## Son durum: temiz git ağacı (hedef)

```text
VermAMG/
├── README.md  LICENSE  .gitignore  setup.sh  requirements.txt
├── scripts/            # vermamg.py + vermamg_lib/ + modules/ (sadece V2 aktif)
├── config/             # env varsayılanları (.bak temizlenmiş)
├── run_templates/      # local_run + hpc_slurm_run_v2 (V2, [FILL]) + README
├── run_configs/        # örnek config'ler
├── examples/           # smoke_precomputed/ (DB'siz uçtan uca demo)
├── pipeline_contracts/ # stage IO sözleşmeleri
├── docs/               # ARCHITECTURE, STAGE_CONTRACTS, INSTALL, PIPELINE_MAP,
│                       # DEV_NOTES, planning/
├── inputs/             # küçük örnek/regresyon FASTA'ları (opsiyonel)
├── resources/          # (gitignored) setup.sh doldurur
├── incoming/  runs/    # (gitignored) lokal veri
```

## Definition of Done (kullanıcı bunu işaretleyerek push eder)
- [ ] Kök dizin temiz; arşive taşınanlar `/d/VermAMG_archive/`'da, git'te yok.
- [ ] 2 V2 şablonu `vermamg.py plan` ile PASS; 665 yok.
- [ ] `examples/smoke_precomputed/` DB'siz çalışır, çıktı üretir, < 25MB.
- [ ] `setup.sh` tek komut; tüm DB/araç/container/python; her yol INSTALL.md ile tutarlı.
- [ ] README 3 adımı net anlatır; tüm link/komut çalışır; V1 atıf yok.
- [ ] `docs/INSTALL.md` her DB için kaynak+hedef+config anahtarı içerir.
- [ ] Doğrulama kapısı 8/8 PASS; tracked boyut < 5MB.
- [ ] LICENSE + README contact'a kullanıcı kendi adını/e-postasını ekledi.

## Açık notlar / Codex'e uyarılar
- Hiçbir şey **silinmeden** önce arşive taşınır (V1 artefaktları). Saf çöp
  (`.bak/__pycache__/"1"`) doğrudan silinebilir.
- `resources/ incoming/ runs/` ASLA taşınmaz/silinmez — pipeline'ın gerçek
  çalışması bunlara bağlı; sadece gitignore.
- Smoke referans kısıtı (Adım 4) en olası takılma noktası — (a) hedef, (b) yedek.
- Derin paket restructure bu planda YOK; ayrı gün (RESTRUCTURE_REPORT.md).
