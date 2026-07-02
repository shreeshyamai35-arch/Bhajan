# Voice Cloning on AWS (GPU) — BhajanForge

Run the RVC voice-cloning GPU server on AWS instead of free Colab. BhajanForge
talks to it through the **same `/convert` contract** as Colab/Kaggle, so no app
code changes — you only edit `.env`.

## Honest cost / setup reality
| | Free Colab | AWS EC2 `g4dn.xlarge` (T4) | Replicate |
|---|---|---|---|
| GPU cost | free | ~$0.50–0.60 / hr | per-second, pay-as-you-go |
| Payment method needed | no | **yes** | yes |
| GPU quota request needed | no | **yes (new accounts start at 0)** | no |
| Always-on | no (session idles out) | yes (while running) | yes |
| Setup effort | low | medium | low |

**For this project right now, free Colab is still the fastest path** because the
AWS account on file has the same payment blocker as Bedrock and new accounts have
0 GPU quota. Use this AWS path once billing + a G-instance quota increase are
approved.

## Files
- `rvc_server.py` — FastAPI server implementing `/health`, `/convert`, `/train`
  (the BhajanForge tunnel contract).
- `ec2_rvc_setup.sh` — run on the instance: installs RVC + pretrained + cloudflared.
- `launch_ec2.ps1` — launches a GPU EC2 box from your PC via AWS CLI.

## Step by step
1. **Billing + quota (your side, one-time):**
   - AWS Console → Billing → add a valid payment method.
   - Service Quotas → EC2 → "Running On-Demand G and VT instances" → request ≥ 4 vCPUs.
     New accounts often start at 0; approval can take hours to ~2 days.
2. **AWS CLI:** install it, run `aws configure` (key/secret/region), create an EC2 key pair.
3. **Launch the box:**
   ```powershell
   cd aws
   .\launch_ec2.ps1 -KeyName <your-key-name> -Region ap-south-1
   ```
4. **Provision + serve** (copy files up, then run setup):
   ```bash
   scp -i <key>.pem rvc_server.py ec2_rvc_setup.sh ubuntu@<ip>:~/
   ssh -i <key>.pem ubuntu@<ip>
   bash ec2_rvc_setup.sh
   cd /opt/rvc && source .venv/bin/activate
   RVC_ROOT=/opt/rvc PORT=7865 python rvc_server.py &
   cloudflared tunnel --url http://localhost:7865     # prints a public https URL
   ```
5. **Train your voice** (on the box, one-time, ~20–40 min for 200 epochs): follow the
   RVC WebUI training steps with 5–15 clean solo-singing clips, producing
   `shyam_voice_v1.pth` (+ `.index`) under `/opt/rvc/assets/weights`.
6. **Point BhajanForge at it** — edit `.env` on your PC:
   ```
   VOICE_PROVIDER=colab_tunnel
   RVC_TUNNEL_URL=https://<the-cloudflared-url>
   ```
   and `config/learning.yaml`:
   ```yaml
   voice_profile:
     active_rvc_model: shyam_voice_v1
   ```
7. **Produce** via the web UI or CLI. Each guide vocal is converted to your voice.
8. **STOP THE BOX** when done — it bills per hour:
   ```powershell
   aws ec2 terminate-instances --instance-ids <id> --region ap-south-1
   ```

## SageMaker alternative
A SageMaker **Notebook instance** (`ml.g4dn.xlarge`) is the same T4 GPU with a
Jupyter UI — you can paste the cells from `notebooks/voice_clone_colab.ipynb`
almost verbatim, then run `rvc_server.py` + cloudflared in a terminal cell.
Same billing + quota prerequisites apply.

## What AWS can NOT do for this project
- **Bedrock** is LLM-only (no voice cloning); also blocked by the same payment issue.
  Lyrics already run on Groq, so Bedrock isn't needed.
- **Polly** is text-to-speech, not voice *cloning* — not a substitute for RVC.
