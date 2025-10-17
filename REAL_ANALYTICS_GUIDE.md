# Real Analytics Data Implementation Guide

This guide explains how to get **real values** for the dashboard analytics instead of mock data.

## Current Implementation Status

### ✅ **Real Data (Live from APIs)**
- **Connection Success**: Calculated from active rooms vs total rooms ratio
- **Connection Minutes**: Estimated from participant join times and current session durations  
- **Platforms**: Inferred from participant metadata, names, and track patterns
- **Connection Types**: Determined from LiveKit connection information

### 🔄 **Enhanced Data Sources**

## Method 1: Real-time Analysis (Currently Implemented)

The dashboard now uses `get_enhanced_analytics()` which:

1. **Analyzes Active Participants**: Examines all current participants across rooms
2. **Extracts Platform Info**: Uses multiple methods to determine client platforms:
   - Participant metadata (if clients set platform info)
   - Participant names (pattern matching for mobile/web indicators)
   - Track patterns (different SDKs have different behaviors)
3. **Calculates Connection Health**: Based on room activity and participant status
4. **Estimates Session Duration**: Using participant join timestamps

### Platform Detection Methods:
```javascript
// Example client-side metadata that helps with platform detection
const metadata = {
  platform: "iOS",           // or "Android", "Web", "React Native"
  client: "livekit-ios",     // SDK identifier
  version: "1.0.0",
  userAgent: navigator.userAgent  // Web clients
}
```

## Method 2: Webhook-Based Analytics (Recommended for Production)

For **accurate historical data**, implement webhook storage:

### Setup Steps:

1. **Configure LiveKit Webhooks**:
```yaml
# livekit.yaml
webhook:
  urls:
    - http://your-dashboard.com/webhook/livekit
  api_key: your_webhook_key
```

2. **Create Webhook Endpoint**:
```python
# app/routes/webhook.py
@router.post("/webhook/livekit")
async def handle_livekit_webhook(request: Request):
    # Verify webhook signature
    # Store events in database
    event = await request.json()
    
    if event['event'] == 'participant_joined':
        # Store participant join with platform info
        pass
    elif event['event'] == 'participant_left':
        # Calculate actual session duration
        pass
```

3. **Database Schema**:
```sql
CREATE TABLE participant_sessions (
    id SERIAL PRIMARY KEY,
    participant_id VARCHAR(255),
    room_name VARCHAR(255),
    platform VARCHAR(50),
    joined_at TIMESTAMP,
    left_at TIMESTAMP,
    duration_minutes INTEGER,
    connection_type VARCHAR(50)
);

CREATE TABLE room_sessions (
    id SERIAL PRIMARY KEY,
    room_name VARCHAR(255),
    created_at TIMESTAMP,
    ended_at TIMESTAMP,
    max_participants INTEGER
);
```

4. **Analytics Queries**:
```python
async def get_webhook_analytics():
    # Real connection success rate
    total_attempts = await db.count("participant_sessions WHERE created_at > NOW() - INTERVAL '24 hours'")
    successful = await db.count("participant_sessions WHERE joined_at IS NOT NULL AND created_at > NOW() - INTERVAL '24 hours'")
    
    # Real platform distribution
    platforms = await db.query("SELECT platform, COUNT(*) FROM participant_sessions WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY platform")
    
    # Real connection minutes
    total_minutes = await db.query("SELECT SUM(duration_minutes) FROM participant_sessions WHERE created_at > NOW() - INTERVAL '24 hours'")
    
    return {
        "connection_success": (successful / total_attempts) * 100,
        "connection_minutes": total_minutes,
        "platforms": dict(platforms),
        "connection_types": {...}
    }
```

## Method 3: External Analytics Integration

Integrate with existing analytics platforms:

### Prometheus + Grafana
```python
# Add metrics collection
from prometheus_client import Counter, Histogram, Gauge

participant_joins = Counter('livekit_participant_joins_total', ['platform', 'room'])
session_duration = Histogram('livekit_session_duration_seconds', ['platform'])
active_participants = Gauge('livekit_active_participants', ['room'])

# In webhook handler
participant_joins.labels(platform=platform, room=room).inc()
session_duration.labels(platform=platform).observe(duration)
```

### Custom Analytics API
```python
# Send events to your analytics service
async def track_participant_event(event_type, participant_data):
    await analytics_client.track({
        'event': event_type,
        'properties': {
            'platform': participant_data.platform,
            'room': participant_data.room,
            'timestamp': participant_data.timestamp
        }
    })
```

## Method 4: Client-Side Analytics (Recommended)

The most accurate approach is client-side tracking:

### Web Client Example:
```javascript
// In your LiveKit client application
const room = new Room();

// Track platform info
room.localParticipant.setMetadata(JSON.stringify({
  platform: 'Web',
  browser: navigator.userAgent,
  sdk: 'livekit-client-js',
  version: '1.0.0'
}));

// Track connection events
room.on(RoomEvent.Connected, () => {
  analytics.track('participant_connected', {
    platform: 'Web',
    connectionType: 'WebRTC',
    timestamp: Date.now()
  });
});

room.on(RoomEvent.Disconnected, () => {
  analytics.track('participant_disconnected', {
    platform: 'Web',
    sessionDuration: sessionStartTime - Date.now(),
    timestamp: Date.now()
  });
});
```

### Mobile Client Example:
```swift
// iOS Swift
let metadata = [
    "platform": "iOS",
    "device": UIDevice.current.model,
    "sdk": "livekit-swift",
    "version": "1.0.0"
]
localParticipant.metadata = try! JSONSerialization.data(withJSONObject: metadata)
```

## Current Demo Data

When no real participants are active, the dashboard shows realistic sample data:

- **Connection Success**: 95.8%
- **Platforms**: Web (12), iOS (5), Android (3), React Native (2)  
- **Connection Types**: WebRTC Direct (15), TURN Relay (7)
- **Connection Minutes**: 237 minutes

## Implementation Priority

1. **✅ Phase 1**: Real-time analysis (Implemented)
2. **🔄 Phase 2**: Client-side metadata enhancement
3. **🔄 Phase 3**: Webhook-based historical data
4. **🔄 Phase 4**: External analytics integration

## Testing Real Data

To see real analytics data:

1. **Join rooms with different clients** (Web, mobile apps)
2. **Set meaningful participant metadata** in your client applications
3. **Use descriptive participant names** (e.g., "ios-user-123", "web-participant")
4. **Create multiple rooms** with various participant counts

The dashboard will automatically detect and analyze this real data!

## Configuration

Enable enhanced analytics in your environment:
```bash
# .env
ENABLE_ENHANCED_ANALYTICS=true
WEBHOOK_ENDPOINT=http://localhost:8000/webhook/livekit
ANALYTICS_RETENTION_DAYS=30
```

This implementation provides a foundation for comprehensive LiveKit analytics that scales from development to production environments.