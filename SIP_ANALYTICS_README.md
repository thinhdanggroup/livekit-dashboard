# Comprehensive LiveKit Dashboard Analytics

This implementation adds comprehensive analytics for all major LiveKit services to the dashboard, leveraging the full capabilities of the LiveKit Python SDK APIs.

## Analytics Implementation Overview

### 1. Room Analytics (`get_room_analytics()`)
**Data Source**: Room Service API (`room_service.py`)

#### Metrics Displayed:
- **Active Rooms**: Number of rooms with participants
- **Total Rooms**: All existing rooms
- **Empty Rooms**: Rooms with no participants  
- **Total Participants**: Sum across all rooms
- **Average Participants**: Per-room average
- **Room Size Distribution**: Chart showing small (1-5), medium (6-20), large (21+) room distribution
- **API Latency**: Response time for room service calls

#### Key Methods Used:
- `list_rooms()` - Get all rooms and their participant counts
- Real-time calculation of room statistics

### 2. Egress Analytics (`get_egress_analytics()`)
**Data Source**: Egress Service API (`egress_service.py`)

#### Metrics Displayed:
- **Active Jobs**: Currently running egress tasks
- **Completed Jobs**: Successfully finished recordings
- **Failed Jobs**: Failed egress attempts
- **Success Rate**: Percentage of successful jobs
- **Egress Types**: Chart showing distribution of room composite, participant, track, and web egress
- **Storage Used**: Estimated storage consumption (mock data)

#### Key Methods Used:
- `list_egress(active=True)` - Get active egress jobs
- `list_egress(active=False)` - Get all recent egress jobs
- Status analysis from `EgressInfo` objects

### 3. Ingress Analytics (`get_ingress_analytics()`)
**Data Source**: Ingress Service API (`ingress_service.py`)

#### Metrics Displayed:
- **Active Streams**: Currently active ingress streams
- **Total Ingress**: All configured ingress endpoints
- **Connection Quality**: Stability percentage (mock data)
- **Stream Types**: Chart showing RTMP, WHIP, URL distribution
- **Average Bitrate**: Stream quality metric (mock data)

#### Key Methods Used:
- `list_ingress()` - Get all ingress configurations
- State analysis from `IngressInfo` objects

### 4. SIP Analytics (`get_sip_analytics()`)
**Data Source**: SIP Service API (`sip_service.py`)

#### Metrics Displayed:
- **Total SIP Trunks**: Combined inbound and outbound trunk count
- **Connection Success**: SIP call success rate
- **Trunk Status**: Chart showing active vs configured trunks
- **Dispatch Rules**: Number of routing rules
- **Call Volume**: Recent call activity (mock data)

#### Key Methods Used:
- `list_inbound_trunk()` - Get inbound SIP trunks
- `list_outbound_trunk()` - Get outbound SIP trunks  
- `list_dispatch_rule()` - Get SIP routing rules

## Dashboard Features

### Visual Components
- **Metric Cards**: Clean, responsive cards showing key statistics
- **Chart.js Integration**: Doughnut charts for data distribution visualization
- **Expandable Sections**: Organized analytics by service type
- **Real-time Data**: Live data fetched from LiveKit APIs

### Responsive Design
- **Mobile-friendly**: Adapts to different screen sizes
- **Grid Layout**: Automatic responsive grid for metric cards
- **Consistent Styling**: Matches existing dashboard theme

## Files Modified

### Backend Implementation
1. **`app/services/livekit.py`**
   - Added `get_room_analytics()` method
   - Added `get_egress_analytics()` method  
   - Added `get_ingress_analytics()` method
   - Enhanced `get_sip_analytics()` method
   - Added comprehensive error handling and debugging

2. **`app/routes/overview.py`**
   - Integrated all analytics data collection
   - Added analytics data to template context
   - Enhanced debug logging

### Frontend Implementation
3. **`app/templates/index.html.j2`**
   - Enhanced Rooms section with detailed analytics
   - Enhanced Egress section with job statistics and charts
   - Enhanced Ingress section with stream analytics
   - Enhanced Telephony section with SIP metrics
   - Added Chart.js visualizations for all services

4. **`app/static/css/style.css`**
   - Added styles for metric details and subtitles
   - Enhanced responsive design

## Real-time Metrics vs Mock Data

### Real-time Data (Live from APIs):
- ✅ Room counts and participant statistics
- ✅ Egress job counts and status
- ✅ Ingress endpoint counts
- ✅ SIP trunk and rule counts
- ✅ API latency measurements

### Mock Data (Requires Additional Infrastructure):
- 🔄 Historical call volume and success rates
- 🔄 Storage usage calculations
- 🔄 Bandwidth utilization
- 🔄 Connection quality metrics
- 🔄 Bitrate measurements

## Error Handling

Each analytics method includes:
- **Try-catch blocks** for API failures
- **Debug logging** for troubleshooting
- **Fallback data** for service unavailability
- **Graceful degradation** when services are disabled

## Future Enhancements

1. **Historical Data**: Store and display trends over time
2. **Real Metrics**: Integrate with monitoring systems for actual bandwidth, quality, etc.
3. **Alerting**: Add threshold-based notifications
4. **Export**: CSV/JSON export functionality
5. **Filtering**: Time-range filtering for analytics data
6. **Caching**: Redis caching for improved performance

## Usage

The comprehensive analytics are automatically displayed when:
- Services are properly configured in environment variables
- LiveKit server is accessible
- API credentials are valid
- Individual services are enabled (e.g., SIP_ENABLED=true)

Each expandable section shows live data specific to that service, providing operators with complete visibility into their LiveKit infrastructure.

## Debugging

Enable debug output by checking server logs for:
- `DEBUG: Fetching [service] analytics...` - Service data collection start
- `DEBUG: [Service] analytics result:` - Returned data structure
- `DEBUG: Error getting [service] analytics:` - Error conditions

This provides comprehensive monitoring and analytics for LiveKit deployments across all major services.