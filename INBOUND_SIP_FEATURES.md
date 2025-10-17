# SIP Inbound Features Implementation

## Overview

This document describes the newly implemented CRUD (Create, Read, Update, Delete) features for SIP Inbound Trunks and Dispatch Rules in the LiveKit Dashboard.

## Features Implemented

### 1. Inbound Trunk Management

#### List Inbound Trunks

- View all configured inbound trunks in a table
- Display: Trunk ID, Name, Phone Numbers, Allowed Addresses, Auth Username

#### Create Inbound Trunk

- Form fields:
  - Trunk Name (optional)
  - Phone Numbers (comma-separated list)
  - Allowed IP Addresses (optional, comma-separated)
  - Allowed Phone Numbers (optional, comma-separated)
  - Auth Username (optional)
  - Auth Password (optional)
  - Metadata (optional)

#### Update Inbound Trunk

- Edit existing trunk properties
- All fields from create form
- Password field: leave empty to keep current password

#### Delete Inbound Trunk

- Confirmation modal before deletion
- Displays trunk name for confirmation

### 2. Dispatch Rule Management

#### List Dispatch Rules

- View all configured dispatch rules in a table
- Display: Rule ID, Name, Trunk IDs count, Room Name, PIN, Agent Name, Hide Phone Number flag

#### Create Dispatch Rule

- Form fields:
  - Rule Name (optional)
  - Trunk IDs (comma-separated list of trunk IDs to apply rule to)
  - Room Name (LiveKit room where calls will be routed)
  - PIN (optional, requires callers to enter PIN)
  - Hide Phone Number (checkbox, hides caller's phone number from participants)
  - **Agent Configuration (optional):**
    - Agent Name (name of the agent to dispatch to the room)
    - Agent Metadata (metadata to pass to the agent)
  - Rule Metadata (optional)

#### Update Dispatch Rule

- Edit existing rule properties
- All fields from create form

#### Delete Dispatch Rule

- Confirmation modal before deletion
- Displays rule name for confirmation

## Technical Implementation

### Backend Changes

#### 1. Service Layer (`app/services/livekit.py`)

Added the following methods to `LiveKitClient` class:

**Inbound Trunk Methods:**

- `list_sip_inbound_trunks()` - List all inbound trunks
- `create_sip_inbound_trunk()` - Create a new inbound trunk
- `update_sip_inbound_trunk()` - Update an existing inbound trunk
- `delete_sip_trunk()` - Delete a trunk (works for both inbound and outbound)

**Dispatch Rule Methods:**

- `create_sip_dispatch_rule()` - Create a new dispatch rule
- `update_sip_dispatch_rule()` - Update an existing dispatch rule
- `delete_sip_dispatch_rule()` - Delete a dispatch rule

#### 2. Routes Layer (`app/routes/sip.py`)

Added the following endpoints:

**Inbound Trunk Endpoints:**

- `GET /sip-inbound` - View page (updated to include trunks and flash messages)
- `POST /sip-inbound/trunk/create` - Create inbound trunk
- `POST /sip-inbound/trunk/update` - Update inbound trunk
- `POST /sip-inbound/trunk/delete` - Delete inbound trunk

**Dispatch Rule Endpoints:**

- `POST /sip-inbound/rule/create` - Create dispatch rule
- `POST /sip-inbound/rule/update` - Update dispatch rule
- `POST /sip-inbound/rule/delete` - Delete dispatch rule

All endpoints include:

- CSRF protection
- Admin authentication requirement
- Error handling with user-friendly messages
- Success/error flash messages with URL-safe encoding

### Frontend Changes

#### 1. Template (`app/templates/sip/inbound.html.j2`)

Completely redesigned with:

**Stats Section:**

- Displays count of inbound trunks
- Displays count of dispatch rules

**Inbound Trunks Section:**

- Table showing all inbound trunks
- "Create Trunk" button
- Edit and Delete buttons for each trunk
- Empty state when no trunks exist

**Dispatch Rules Section:**

- Table showing all dispatch rules
- "Create Rule" button
- Edit and Delete buttons for each rule
- Empty state when no rules exist

**Modals:**

- Create Trunk Modal (form with all fields)
- Edit Trunk Modal (pre-filled form)
- Delete Trunk Confirmation Modal
- Create Rule Modal (form with all fields)
- Edit Rule Modal (pre-filled form)
- Delete Rule Confirmation Modal

**JavaScript Functions:**

- `editTrunk()` - Opens edit modal with trunk data
- `confirmDeleteTrunk()` - Opens delete confirmation modal
- `editRule()` - Opens edit modal with rule data
- `confirmDeleteRule()` - Opens delete confirmation modal
- Auto-dismiss flash messages after 5 seconds

## User Experience Features

### Flash Messages

- Success messages (green) for successful operations
- Error messages (red) for failed operations
- Auto-dismiss after 5 seconds
- Manual dismiss via close button

### Form Validation

- Required fields are clearly marked
- Helper text explains field formats
- Comma-separated lists for multiple values
- Password fields hide input

### Responsive Design

- Tables are responsive and scrollable
- Modals work on all screen sizes
- Buttons use Bootstrap grid system

### Error Handling

- Backend errors are caught and displayed to users
- Full stack traces printed to console for debugging
- User-friendly error messages

## API Integration

The implementation uses the LiveKit Python SDK's SIP service methods:

### Inbound Trunks

```python
# Create
lk.sip.create_inbound_trunk(CreateSIPInboundTrunkRequest)

# Update
lk.sip.update_inbound_trunk(trunk_id, trunk_info)

# List
lk.sip.list_inbound_trunk(ListSIPInboundTrunkRequest)

# Delete
lk.sip.delete_trunk(DeleteSIPTrunkRequest)
```

### Dispatch Rules

```python
# Create
lk.sip.create_dispatch_rule(CreateSIPDispatchRuleRequest)

# Update
lk.sip.update_dispatch_rule(rule_id, rule_info)

# List
lk.sip.list_dispatch_rule(ListSIPDispatchRuleRequest)

# Delete
lk.sip.delete_dispatch_rule(DeleteSIPDispatchRuleRequest)
```

## Usage Examples

### Creating an Inbound Trunk

1. Navigate to `/sip-inbound`
2. Click "Create Trunk" button
3. Fill in the form:
   - Trunk Name: "My Inbound Trunk"
   - Phone Numbers: "+1234567890, +0987654321"
   - Allowed Addresses: "192.168.1.0/24" (optional)
   - Auth Username: "myuser" (optional)
   - Auth Password: "mypassword" (optional)
4. Click "Create Trunk"
5. Success message appears and page refreshes with new trunk

### Creating a Dispatch Rule

1. Navigate to `/sip-inbound`
2. Click "Create Rule" button
3. Fill in the form:
   - Rule Name: "Main Office Rule"
   - Trunk IDs: "trunk-abc123, trunk-def456"
   - Room Name: "conference-room-1"
   - PIN: "1234" (optional)
   - Hide Phone Number: Check if desired
   - **Agent Name: "inbound-agent"** (optional - agent to dispatch)
   - **Agent Metadata: "greeting=welcome"** (optional - metadata for agent)
4. Click "Create Rule"
5. Success message appears and page refreshes with new rule

## Security Considerations

- All endpoints require admin authentication
- CSRF tokens protect against cross-site request forgery
- Passwords are transmitted securely (HTTPS recommended)
- Input validation on both frontend and backend
- SQL injection prevention through ORM/SDK usage

## Testing Recommendations

### Manual Testing

1. Test creating trunks with various field combinations
2. Test updating trunks and verify changes persist
3. Test deleting trunks and verify they're removed
4. Test creating rules with different trunk IDs
5. Test updating rules and verify changes persist
6. Test deleting rules and verify they're removed
7. Test error conditions (invalid input, network errors)
8. Test flash message display and auto-dismiss

### Automated Testing

Consider adding tests for:

- Service layer methods (unit tests)
- Route handlers (integration tests)
- Template rendering (frontend tests)
- Error handling scenarios

## Future Enhancements

Potential improvements:

1. Bulk operations (create/delete multiple items)
2. Search and filter functionality
3. Pagination for large lists
4. Export/import configuration
5. Validation of phone number formats
6. IP address format validation
7. Real-time updates using WebSockets
8. Audit log of changes
9. Trunk and rule templates
10. Better visualization of trunk-rule relationships

## Notes

- The `delete_sip_trunk` method works for both inbound and outbound trunks
- Trunk IDs and Rule IDs are displayed truncated (first 16 characters) for better UI
- Empty fields in forms are handled gracefully (None/empty string)
- Protobuf field type warnings are suppressed with `# type: ignore[attr-defined]` comments
- All CRUD operations provide immediate user feedback via flash messages

## Agent Configuration Feature

### Overview

Dispatch rules now support **automatic agent dispatch** when inbound calls are received. This enables powerful automation scenarios where AI agents or services can automatically join SIP calls.

### Features

- **Automatic agent dispatch**: Agents are automatically dispatched to the LiveKit room when a call arrives
- **Agent metadata**: Pass custom metadata to agents for job configuration
- **Flexible configuration**: Different agents can be configured for different dispatch rules
- **Optional**: Agent configuration is completely optional - rules work without agents
- **Easy removal**: Simply clear the agent name field to remove agent configuration

### How It Works

When a dispatch rule has an agent configured:

1. An inbound SIP call triggers the dispatch rule
2. The call is routed to the specified LiveKit room
3. The configured agent is automatically dispatched to join the room
4. Agent receives the metadata specified in the rule configuration
5. Agent can process the call according to its implementation

### Configuration Fields

**Agent Name** (required for agent dispatch):
- The name of the agent to dispatch
- Must match the agent name configured in your agent service
- Example: `inbound-agent`, `call-transcriber`, `voice-assistant`

**Agent Metadata** (optional):
- Custom metadata to pass to the agent
- Can be used for job dispatch configuration
- Example: `{"greeting": "welcome", "language": "en"}`

### Use Cases

1. **Automated Customer Service**
   - Agent answers and handles inbound calls
   - Provides interactive responses to callers
   - Routes calls based on customer input

2. **Call Transcription**
   - Agent joins to transcribe the conversation in real-time
   - Provides live captions or records transcript

3. **Call Recording**
   - Agent automatically records incoming calls
   - Stores recordings with metadata

4. **IVR Systems**
   - Agent provides interactive voice response
   - Collects information from callers
   - Routes to appropriate departments

5. **Call Analytics**
   - Agent analyzes call sentiment
   - Tracks conversation metrics
   - Provides real-time insights

### UI Enhancements

**Table Display:**
- New "Agent" column shows the configured agent name
- Robot icon (🤖) indicates agent configuration
- "No Agent" displayed when no agent is configured

**Create/Edit Modals:**
- New "Agent Configuration" section with visual separator
- Agent Name input field
- Agent Metadata textarea field
- Helpful tooltips and descriptions

### Technical Details

**API Integration:**
```python
# Agent configuration is passed via room_config
rule_info.room_config = api.RoomConfiguration(
    agents=[api.RoomAgentDispatch(
        agent_name=agent_name,
        metadata=agent_metadata or "",
    )]
)
```

**Update Behavior:**
- Providing an empty agent_name removes the agent configuration
- Agent metadata is optional
- Configuration persists across rule updates

## Related Files

- `/app/services/livekit.py` - Service layer implementation (includes agent configuration)
- `/app/routes/sip.py` - Route handlers (handles agent form fields)
- `/app/templates/sip/inbound.html.j2` - Frontend template (agent UI components)
- `/app/security/basic_auth.py` - Authentication
- `/app/security/csrf.py` - CSRF protection
