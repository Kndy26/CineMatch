# CineMatch

CineMatch adalah final project untuk menemukan film serupa dari satu hingga lima judul pilihan. Aplikasi ini menggabungkan sistem rekomendasi berbasis konten, pencarian katalog MovieLens, dan riwayat yang dapat dipakai ulang sebagai template.

**Stack** · Python 3.11 · FastAPI · Jinja2 · PostgreSQL · SQLAlchemy · Alembic · scikit-learn

## Fitur

- **Discover** menyediakan autocomplete judul, filter genre, dan hingga lima rekomendasi dengan skor kemiripan.
- **History** menyimpan pilihan dan hasil di PostgreSQL. Sesi dapat dicari, dipakai ulang, atau dihapus tanpa akun.
- **Film Populer** mengurutkan katalog berdasarkan jumlah rating historis. Home juga menampilkan grafik evaluasi model.
- **Metadata film** dapat diperkaya dengan poster dan sinopsis melalui TMDB.

## Cara kerja rekomendasi

Pipeline mengubah genre menjadi vektor multi-hot dan tag menjadi fitur TF-IDF. K-Nearest Neighbors mencari tetangga menggunakan cosine distance. Untuk beberapa film pilihan, aplikasi mengambil kandidat bergiliran dari tiap judul, mengecualikan film yang sudah dipilih, lalu mengurutkan hasil berdasarkan skor kemiripan tertinggi terhadap salah satu input. [Notebook eksplorasi dan pelatihan](ml/training.ipynb)

Evaluasi offline membandingkan KNN dengan baseline popularitas pada **135.451 pengguna** MovieLens 20M. Setiap pengguna diwakili satu film positif dari bagian awal riwayat. Rekomendasi dibandingkan dengan film yang diberi rating minimal 4 pada bagian terbaru.

| Metrik | KNN | Baseline popularitas |
| --- | ---: | ---: |
| Precision@5 | 0,46% | 6,75% |
| Recall@5 | 0,28% | 3,63% |
| Hit Rate@5 | 2,07% | 24,15% |
| NDCG@5 | 0,0060 | 0,0746 |

Baseline popularitas lebih sering menemukan kembali film yang disukai dalam riwayat uji. Discover menggunakan KNN untuk menemukan judul dengan genre dan tag yang serupa. Grafik Home membaca laporan evaluasi yang dihasilkan pipeline.

## Menjalankan secara lokal

Siapkan **Python 3.11** dan **PostgreSQL 17**. Jalankan perintah berikut dari root repositori.

### 1. Pasang dependensi

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Konfigurasi PostgreSQL

Di `psql`, sambungkan ke database `postgres` sebagai administrator. Buat role aplikasi dan database khusus CineMatch. `\password` meminta password secara interaktif. [Dokumentasi psql](https://www.postgresql.org/docs/17/app-psql.html)

```text
CREATE ROLE cinematch LOGIN;
\password cinematch
CREATE DATABASE cinematch OWNER cinematch;
```

Salin template konfigurasi bila `.env` belum ada. Isi `DATABASE_URL` dengan host, port, dan kredensial lokal. Template memakai port `5432`. Lakukan URL encoding jika password memuat karakter khusus.

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

> **Catatan (PostgreSQL Portabel `.postgres`):** Jika Anda menggunakan instance PostgreSQL portabel di folder `.postgres/` (port `55432`) dan muncul error `503 Service Unavailable` (*"Database tidak tersedia."*) setelah komputer/server restart, pastikan server PostgreSQL sudah dinyalakan sebelum menjalankan aplikasi:
>
> ```powershell
> .\.postgres\pgsql\bin\pg_ctl.exe -D .\.postgres\data -l .\.postgres\server.log start
> ```
>
> Untuk memeriksa status atau menghentikan server PostgreSQL portabel:
>
> ```powershell
> .\.postgres\pgsql\bin\pg_ctl.exe -D .\.postgres\data status
> .\.postgres\pgsql\bin\pg_ctl.exe -D .\.postgres\data stop
> ```

### 3. Bangun artefak model

Unduh **MovieLens 20M** dari GroupLens (via Kaggle) dan ekstrak file CSV langsung ke `ml/data/raw/`. Tambahkan `--data-dir <path>` pada perintah pelatihan jika dataset berada di folder lain. Pipeline menyimpan model, katalog, matriks fitur, dan evaluasi di `ml/artifacts/`. [Unduh MovieLens 20M (Kaggle)](https://www.kaggle.com/datasets/grouplens/movielens-20m-dataset)

```powershell
.\.venv\Scripts\python.exe -m ml.train
```

Untuk menjalankan notebook secara interaktif, pasang `ipykernel` dan `matplotlib` di virtual environment. Gunakan salinan seperti `ml/training.executed.ipynb` untuk menyimpan hasil eksekusi lokal.

### 4. Terapkan migrasi dan mulai aplikasi

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Buka [CineMatch](http://127.0.0.1:8000/), [dokumentasi API](http://127.0.0.1:8000/docs), atau [status database](http://127.0.0.1:8000/health/db). Untuk mencoba alur rekomendasi, pilih *Interstellar* dan *Toy Story* di Discover. Hasilnya mencakup *Gravity* dan *Toy Story 2*.

## Konfigurasi opsional

| Variabel atau file | Pemakaian |
| --- | --- |
| `TMDB_READ_ACCESS_TOKEN` | Isi di `.env` dengan API Read Access Token, lalu restart FastAPI. Poster dan sinopsis diambil melalui server berdasarkan ID TMDB yang tersedia di katalog. |
| `app/data/team.json` | Salin `app/data/team.example.json` untuk mengatur profil tim lokal. Foto profil lokal dapat diletakkan di `app/static/images/team/`. |
| `CINEMATCH_TEST_DATABASE_URL` | Variabel terminal untuk menjalankan uji integrasi pada database PostgreSQL khusus tes. |

Tanpa token TMDB, aplikasi memakai katalog lokal dengan gambar pengganti jika poster tidak tersedia. Proyek berjalan di localhost. [Autentikasi TMDB](https://developer.themoviedb.org/docs/authentication-application)

## Pengujian

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m alembic check
```

Siapkan artefak model sebelum menjalankan tes API. Untuk uji integrasi, buat database tes, jalankan `alembic upgrade head` dengan `DATABASE_URL` database tersebut, lalu isi `CINEMATCH_TEST_DATABASE_URL` di terminal saat menjalankan tes.

## Struktur repositori

```text
app/
  routers/       Halaman dan endpoint API
  services/      Rekomendasi dan metadata film
  models/        Skema ORM PostgreSQL
  templates/     Halaman Jinja2
  static/        CSS, JavaScript, font, dan aset antarmuka
ml/              Notebook, pipeline pelatihan, dan evaluasi
migrations/      Riwayat migrasi Alembic
tests/           Uji model, API, metadata, dan PostgreSQL
.env.example     Template konfigurasi
```

## Sumber data dan aset

MovieLens 20M disediakan oleh **GroupLens**. Dataset dan artefak hasil pelatihan dibuat atau disimpan secara lokal. Metadata tambahan dan poster yang diambil oleh aplikasi bersumber dari **TMDB**. [Ketentuan MovieLens 20M](https://files.grouplens.org/datasets/movielens/ml-20m-README.html) · [Kredit TMDB](https://developer.themoviedb.org/docs/faq)
