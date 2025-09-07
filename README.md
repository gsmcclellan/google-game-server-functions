- Install dependencies
```bash
sudo apt update
sudo apt install -y pip python3-venv

```
- Create venv
```bash
 python3 -m venv .venv
source .venv/bin/activate
```
- Install requirements
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```
- To deactivate venv
```bash
deactivate
```

- Configure env variables
 Create `.env.yaml` file with env configuration
```yaml
INSTANCE_NAME: awesomegame-1
ZONE: us-west1-a
TRIGGER_TOKEN: "change-me-or-use-secret-manager"
ALLOWED_ORIGIN: "*"
```

- gcloud defaults
```bash
# Make gen2 the default for first-time deployments
gcloud config set functions/gen2 true

# Default regions (handy if you always use the same one)
gcloud config set functions/region us-west1
gcloud config set run/region us-west1
```

- Deploy
- ```bash
 gcloud functions deploy start_valheim --trigger-http --runtime python311 --env-vars-file .env.yaml
```