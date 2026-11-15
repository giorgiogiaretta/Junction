# D — Architecture diagrams (Mermaid)

Render with any Mermaid viewer (GitHub renders them inline). Colours: Rokoko = orange, NVIDIA = green, Google = blue, Verda = purple, Unitree/Aalto = grey.

## 1. End-to-end pipeline: glove → camera → vote → cap → hand

```mermaid
flowchart LR
  classDef rokoko fill:#ffe0c2,stroke:#e66a00,color:#000
  classDef nvidia fill:#d9f2c2,stroke:#76b900,color:#000
  classDef google fill:#d2e3fc,stroke:#1a73e8,color:#000
  classDef verda fill:#e6d8f7,stroke:#6c3fc4,color:#000
  classDef robot fill:#e8e8e8,stroke:#555,color:#000

  G[Smartgloves II + Coil Pro]:::rokoko --> C[rgmp_client.py<br/>83 Hz, 0 dropouts]:::rokoko
  CAM[Head camera<br/>G1 RealSense / operator DJI]:::robot --> P[ai/perceive.py<br/>find + crop + locate]
  P --> N[Nemotron 3.5 Super VL<br/>0.22 s]:::nvidia
  P --> GM[Gemma 4 / PaliGemma 2]:::google
  P --> COL[colour rule]
  N --> V[ai/recognize.py<br/>fragile-first vote]
  GM --> V
  COL --> V
  V --> CAP[ai/object_profile.py<br/>cap_for_votes]
  C --> R[finger_map + Dex3 retargeting]:::robot
  CAP --> R
  R --> H[G1 Dex3 hand<br/>MuJoCo sim / real G1]:::robot
  H --> EP[recorded episode]:::rokoko --> J[Gemini judge<br/>after the run]:::google
```

## 2. Fragile-first vote, counted per model family

```mermaid
flowchart TD
  classDef nvidia fill:#d9f2c2,stroke:#76b900,color:#000
  classDef google fill:#d2e3fc,stroke:#1a73e8,color:#000
  F[one head-camera frame] --> K1[NVIDIA key: Nemotron]:::nvidia
  F --> K2[Google key: Gemma 4 or PaliGemma<br/>two models = ONE key]:::google
  F --> K3[colour rule: veto only]
  K1 & K2 & K3 --> Q1{any credible vote says egg?}
  Q1 -- yes --> EGG[egg: gentle cap]
  Q1 -- no --> Q2{both families say stress ball,<br/>confidence >= 0.9?}
  Q2 -- yes --> FULL[stress ball: full closure]
  Q2 -- no --> Q3{any answer at all?}
  Q3 -- no / timeout / breaker open --> CONS[unknown: conservative cap]
  Q3 -- yes --> SHARED[shared egg/ball cap]
```
Measured on our 50 photos: 3 of 3 Nemotron/Gemma disagreements were exactly one model's error; the photo two models got wrong (egg-012) was saved by the third model's "egg".

## 3. Two safety layers: simulation rule vs real robot

```mermaid
flowchart LR
  subgraph SIM["Layer 1: model authority (simulation, ai/object_profile.py)"]
    S1[egg and stress ball share one cap] --> S2[full closure only if 2 families agree<br/>or the operator sets it]
    S2 --> S3[can: not supported, low cap]
  end
  subgraph REAL["Layer 2: hard caps on the real G1 (g1/live_policy_v2_vision.py)"]
    R1[operator declares the object] --> R2[hard caps: egg 0.50 · empty can 0.90 · ball 1.0]
    R2 --> R3[camera label can only LOWER the cap]
    R3 --> R4[organisers' safety filter on every command]
  end
  SIM -. same idea, stricter on hardware .-> REAL
```
Why two layers: in simulation the models are allowed to decide, under the two-family rule. On the real robot the operator decides the ceiling and vision can only make the hand gentler. The vision → cap path on the real robot has been tested on simulated frames only.

## 4. Where each sponsor's technology sits

```mermaid
flowchart LR
  classDef rokoko fill:#ffe0c2,stroke:#e66a00,color:#000
  classDef nvidia fill:#d9f2c2,stroke:#76b900,color:#000
  classDef google fill:#d2e3fc,stroke:#1a73e8,color:#000
  classDef verda fill:#e6d8f7,stroke:#6c3fc4,color:#000
  classDef robot fill:#e8e8e8,stroke:#555,color:#000
  A[Rokoko: motion in<br/>gloves, Coil Pro, SDK stream]:::rokoko --> B[NVIDIA: fast eyes<br/>Nemotron on the Verda endpoint]:::nvidia
  B --> C[Google: second key + voice<br/>Gemma 4, PaliGemma]:::google
  C --> D[Verda: our own GPU<br/>PaliGemma self-hosted, EU]:::verda
  D --> E[Unitree G1 + Aalto runner:<br/>the body, safety filter]:::robot
  E --> F[Google Gemini: slow judge<br/>labels the recorded episode]:::google
  F --> A
```
