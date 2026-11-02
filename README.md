# CPU инференс vLLM

vLLM 0.27.0, Qwen2.5-0.5B-Instruct, float32. Веса скачивает отдельный rootless initContainer и сохраняет на PVC. При повторном запуске используется локальный кэш.

## Запуск

Нужны Docker с Linux-контейнерами, Minikube и kubectl. Платформа: Linux x86_64 с AVX2 или AVX512. Для кластера: 6 CPU и 12 ГиБ RAM.

В Windows с запущенным Docker Desktop:

```powershell
.\start-local.ps1
```

Скрипт создаёт API-токен в `.env` и запускает проброс порта. Для закрытой модели укажите HF_TOKEN в `.env`.

Ручной запуск в Bash:

```bash
minikube start --driver=docker --cpus=6 --memory=12288 --disk-size=30g
minikube image build -t inference-cpu:0.27.0-3 .
minikube image build -f Dockerfile.download -t model-download:1 .

read -rs -p 'API token: ' API_TOKEN
export API_TOKEN
kubectl create secret generic inference-secrets \
  --from-literal=API_TOKEN="$API_TOKEN" \
  --from-literal=HF_TOKEN="${HF_TOKEN:-}"

kubectl apply -k k8s
kubectl rollout status deployment/inference --timeout=1800s
kubectl port-forward service/inference 8000:8000
```

Для закрытой модели нужно задать переменную HF_TOKEN перед созданием Secret.

Запрос во втором терминале с тем же API_TOKEN:

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $API_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen","messages":[{"role":"user","content":"What is Kubernetes?"}],"max_tokens":32}'
```

Настройки меняются в `k8s/serve.yaml` и `k8s/kustomization.yaml`, затем применяется `kubectl apply -k k8s`.

## Нагрузочный тест

При работающем API:

```bash
python benchmark.py --requests 8 --concurrency 2 --max-tokens 32 --output benchmark-results.json
```

Токен берётся из API_TOKEN или `.env`. Для каждого размера промпта: прогрев, 8 запросов, 2 одновременно, ответ по 32 токена. Промпты уникальны между запусками. TTFT — время до первого текстового фрагмента, Latency — до конца ответа. Throughput — выходные токены за время всего сценария. В таблице TTFT и Latency усреднены; прогрев исключён.

Результаты от 2 ноября 2026 года: Intel Core i9-12900K, Windows 11 / WSL2, Minikube. Лимиты сервера: 4 CPU, 8 ГиБ RAM, KV-кэш 1 ГиБ, контекст 2048, `max-num-seqs=4`, `max-num-batched-tokens=2048`.

| Промпт | Средний вход, токенов | TTFT, с | Latency, с | Throughput, токенов/с |
| --- | ---: | ---: | ---: | ---: |
| Короткий | 82,8 | 1,162 | 11,310 | 5,64 |
| Длинный | 1151,6 | 7,115 | 19,170 | 3,33 |

Все запросы завершились без ошибок. Отдельные замеры — в `benchmark-results.json`.

## Повышение Throughput

Много коротких запросов: проверить увеличение `max-num-seqs` с 4 до 8 или 16 и достаточный бюджет `max-num-batched-tokens`. Это увеличивает batch, но на CPU может ухудшить задержки, поэтому результат нужно измерять.

Мало запросов с большим контекстом: увеличить `max-model-len` до нужной длины и при необходимости выделить больше RAM и `VLLM_CPU_KVCACHE_SPACE`. Использовать `enable-chunked-prefill`, сравнить `max-num-batched-tokens=2048` и 4096. При нехватке памяти уменьшить `max-num-seqs`; для общих длинных префиксов использовать `enable-prefix-caching`.

