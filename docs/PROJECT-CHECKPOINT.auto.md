# Auto Checkpoint (pre-compaction snapshot)

- Time: 2026-11-11T15:37:35.030Z
- Session: ses_f89262437ffeyTgTBujokgXJjJ
- Project: D:\AI\Projects\transcribe-engine

## Recent user prompts (tail)
- **user**: fix PS D:\AI\Projects\transcribe-engine> python -m src.cli playlist https://www.youtube.com/playlist?list=PLuMb272uIN_TodIjkwktMueyJ4vT4NaSy  --to-parquet data/output/segments.parquet
2026-11-11 17:10:44,408 INFO playlist: 160 videos
W1111 17:11:17.246000 31504 site-packages\torch\distributed\elastic\multiprocessing\redirects.py:29] NOTE: Redirects are currently not supported in Windows or MacOs.
W1111 17:11:24.770000 31504 site-packages\torch\utils\flop_counter.py:29] triton not found; flop counting will not work for triton kernels
Loading weights: 100%|███████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████████| 2150/2150 [00:06<00:00, 311.80it/s]
Traceback (most recent call last):
  File "D:\AI\Projects\transcribe-engine\src\hub.py", line 92, in load_local_first
    return loader(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Kandil\AppData\Local\Programs\Python\Python312\Lib\site-packages\coherex\__init__.py", line 21, in load_model
    return asr.load_model(*args, **kwargs)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "C:\Users\Kandil\AppData\Local\Programs\Python\Python312\Lib\site-packages\coherex\asr.py", line 266, in load_model
    ).to(target_device)
      ^^^^^^^^^^^^^^^^^
  File "C:\Users\Kandil\AppData\Local\Programs\Python\Python312\Lib\site-packages\transformers\modeling_utils.py", line 3710, in to
    return super().to(*args, **kwargs)
           ^^^^^^^^^^^^

> Regenerate a curated checkpoint with /checkpoint.