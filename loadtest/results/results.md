| Prompt | Concurrency | Requests | Prompt tok | Output tok | TTFT p50, s | TTFT p95, s | Latency p50, s | Latency p95, s | TPOT p50, ms | Throughput, tok/s | Throughput, req/s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| short | 1 | 8 | 69 | 64 | 6.82 | 7.27 | 16.28 | 16.83 | 150 | 3.9 | 0.06 |
| short | 4 | 8 | 68 | 64 | 26.60 | 27.63 | 59.33 | 60.09 | 515 | 4.3 | 0.07 |
| long | 1 | 8 | 1600 | 64 | 163.32 | 164.80 | 173.43 | 175.01 | 158 | 0.4 | 0.01 |
| long | 4 | 8 | 1601 | 64 | 330.92 | 701.16 | 693.87 | 1115.91 | 5406 | 0.4 | 0.01 |
