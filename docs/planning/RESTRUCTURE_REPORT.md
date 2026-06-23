# YENİDEN YAPILANDIRMA RAPORU — VermAMG Mimari Düzeni

> Soru (kullanıcı): "Yeniden yapılandıracak olsak nasıl bir plan kurmamız gerekir,
> neye dikkat etmemiz gerekir?" Bu rapor mevcut düzeni tarar, hedef düzeni önerir,
> riskleri ve güvenli göç yolunu çıkarır. **Uygulama ayrı bir gün** yapılır;
> bu yalnızca analiz/karar belgesidir.

Tarih: 2026-06-22.

---

## 1. Mevcut düzenin değerlendirmesi

### İyi olan
- `scripts/vermamg_lib/` çekirdeği temiz ve modüler: 8 `.py` dosyası
  (config, run_context, stage_registry, stage_contracts, validators, executor,
  state, __init__). Mimari sağlam: tek guarded orchestrator + stage registry +
  IO sözleşmeleri.
- Stage'ler numaralı ve sözleşmeli (`stage_contracts.py`), resume/checkpoint var.
- V2 run-root modeli (`runs/{project}/{run}/work|results|exports`) düzgün.

### Kafa karıştıran / zayıf
- `scripts/modules/` karışık: 63 `.py` (V2 aktif) + 21 `.sh` (çoğu V1 legacy) +
  13 `.bak/.before_*` (çöp). Yeni gelen biri hangisinin canlı olduğunu anlayamaz.
- `scripts/master/` neredeyse tamamen V1 shell pipeline + onlarca `.bak`.
- `scripts/{qc,submit,utils,provenance}/` — V1/V2 karışımı, belirsiz rol.
- Kökte V1 numaralı çıktı klasörleri (TASIMA.md ile temizlenecek).
- Yol referansları kodda **string literal** olarak gömülü (bkz. §3) — düzen
  değişimini kırılgan yapar.

---

## 2. Önerilen hedef düzen (profesyonel, paket-benzeri)

```
VermAMG/
├── README.md  LICENSE  .gitignore  setup.sh  requirements.txt
├── pyproject.toml                 # paketleme + konsol girişi: `vermamg`
├── src/vermamg/                   # = bugünkü scripts/vermamg_lib/
│   ├── __init__.py  cli.py        # cli.py = bugünkü scripts/vermamg.py
│   ├── core/  (config, run_context, state)
│   ├── pipeline/ (stage_registry, stage_contracts, validators, executor)
│   └── paths.py                   # YENİ: TÜM yol literalleri tek yerde (§3)
├── src/vermamg/stages/            # = bugünkü scripts/modules/*.py (sadece V2)
│   ├── intake/   (00a_fasta_intake, 00b_plan_fasta_batches)
│   ├── backend/  (00c_plan_backend_jobs, 00d_run_colabfold, 00e_run_foldseek)
│   ├── import_/  (import_precomputed_*)
│   ├── structural/ (06b/07b/08/09* foldseek+p2rank)
│   ├── decision/ (11/12/13 karar+rulebook)
│   └── export/   (14/15 export)
├── config/                        # env varsayılanları
├── run_templates/                 # local + HPC kullanıcı şablonları
├── examples/                      # smoke verisi + config
├── docs/
└── tests/                         # YENİ: smoke + birim testleri
```

Eski `scripts/{master,qc,submit,utils,provenance}` ve `modules/*.sh` (V1) →
arşive veya `legacy/` (gitignore). Sadece V2'de gerçekten çağrılan dosyalar taşınır.

---

## 3. EN BÜYÜK RİSK: gömülü yol referansları

Sayımlar (mevcut kod):
| Referans türü | Adet | Nerede |
|---|---:|---|
| `project_path("scripts/modules/...")` | 66 | executor stage dispatch |
| `"scripts/modules/"` string | 150 | vermamg_lib geneli |
| `ctx.run_path("02_foldseek/...")` vb. | 152 | executor |
| Gömülü göreli yol literali (`"04_p2rank/..."` vb.) | 126 | executor |

**Anlamı:** Bir dosyayı taşımak/yeniden adlandırmak, kodun içindeki yüzlerce
string'i kırar. `grep`+değiştir riskli (yanlış eşleşme, sessiz bozulma).

**Dikkat edilecekler:**
1. Modül dispatch yolları (`project_path("scripts/modules/00a_...")`) — dosya
   taşınınca hepsi güncellenmeli.
2. Run-root göreli çıktı yolları (`run_path("02_foldseek/...")`) — bunlar
   downstream sözleşmeleri; değişirse 320'ye kadar her stage kırılır.
3. Config göreli yolları (`inputs.fasta`, `colabfold.query_pdb_dir` ...) — örnek
   config'ler ve şablonlar güncellenmeli.
4. `stage_contracts.py` ve `stage_registry.py`'deki yol literalleri — IO
   doğrulayıcı ve beklenen-çıktı listeleri.
5. `__pycache__` ve import yolları (`from .config import ...`) — paket adı
   `vermamg` olunca importlar değişir.

---

## 4. Güvenli göç stratejisi (yapıldığında)

**İlke: önce merkezileştir, sonra taşı, her adımda doğrula.**

- **Adım 0 — Test ağı:** `tests/` altında smoke (precomputed örnek 320'ye kadar
  PASS) + `validate-stage` + `plan` testleri. Bu, refactor sırasında "kırıldı mı?"
  sorusunu saniyede yanıtlar. Refactor'a BUNSUZ başlanmaz.
- **Adım 1 — paths.py:** Tüm run-root göreli yol literallerini tek modülde
  sabit/fonksiyon yap (`P.foldseek_all_hits(mode)` gibi). executor onları çağırsın.
  Bu, 126+152 literali tek yere toplar; sonraki taşımalar tek dosyada olur.
- **Adım 2 — stage kayıt tablosu:** Modül dosya yollarını `stage_registry`'de
  veri olarak tut (her stage → modül yolu). executor dispatch string'leri yerine
  registry'den okusun. 66+150 referans tek tabloya iner.
- **Adım 3 — dosya taşıma:** Yalnız §1 ve §2'deki temiz adımlardan sonra
  `git mv` ile fiziksel taşıma. Her taşımadan sonra smoke testi koş.
- **Adım 4 — paketleme:** `pyproject.toml` + `vermamg` konsol komutu; `python
  scripts/vermamg.py` yerine `vermamg run ...`. Geriye-uyum için ince bir
  `scripts/vermamg.py` shim bırakılabilir.
- **Adım 5 — legacy ayıkla:** V1 `.sh`/master/qc/submit yalnız gerçekten
  kullanılmıyorsa `legacy/`'ye. Kullanım `grep` ile kanıtlanır, tahminle silinmez.

---

## 5. Tavsiye (öncelik & zamanlama)

| Faz | İş | Risk | Ne zaman |
|---|---|---|---|
| **1 (bugün)** | TASIMA.md: çöp sil, V1 arşivle, git scaffolding, README/şablon/smoke | Düşük | Hemen — git-ready bunu gerektirir |
| **2 (sonra)** | tests/ smoke ağı + paths.py merkezileştirme | Orta | Refactor'dan ÖNCE |
| **3 (gündüz)** | src/vermamg paket taşıması + dispatch tablolaştırma | Yüksek | Test ağı kurulunca |
| **4 (opsiyonel)** | pyproject + `vermamg` CLI + legacy ayıklama | Orta | Paket sonrası |

**Sonuç:** Bugünkü git-ready hedefi için **derin yeniden yapılandırmaya gerek yok**
— Faz 1 (TASIMA.md) tek başına temiz, profesyonel, çalışan bir repo verir. Asıl
paket-restructure (Faz 3) en iyi şekilde önce test ağı + paths.py ile yapılır;
aksi halde 400+ string referansı sessizce kırma riski yüksektir. Lab'a göndermek
için Faz 1 yeterli ve etkileyici; Faz 2–4 "sürekli geliştiriyorum" mesajını
güçlendiren sonraki adımlardır.
