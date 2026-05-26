# AI Glasses Pipeline Test Suite
## Testing with Meta Ray-Ban Gen 2 (borrowed) → Production with Mentra Live

### What This Tests
This test suite validates the complete Stage 4 (phone-side ML inference) pipeline
WITHOUT needing actual glasses connected. We simulate the glasses input by:
1. Taking photos with phone camera (simulates glasses camera capture)
2. Running the full ML inference chain on phone
3. Uploading results to Supabase (real cloud backend)

### Test Phases
- Phase A: Food photo → ML inference → nutrition lookup (offline, no glasses needed)
- Phase B: Phone camera as glasses simulator → full pipeline → Supabase
- Phase C: Meta Ray-Ban Gen 2 BLE → phone → full pipeline → Supabase

### Setup
```bash
cd backend
pip install -r glasses_test/requirements.txt
python -m glasses_test.test_pipeline
```
