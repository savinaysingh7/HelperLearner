# HelperLearner

A platform where users can post help requests for specific skills, offering "Knowledge Points" (KP) as a bounty.

## Features
- **Knowledge Point System**: Earn KP by helping others and spend them to get help.
- **Escrow System**: KP are deducted and held in escrow when a request is posted.
- **Private Discussion**: Once a request is claimed, the requester and helper can communicate via private comments.
- **Pagination & Search**: Easily find requests by skill or keyword.
- **Transaction Safety**: Uses `select_for_update` to prevent race conditions during KP transfers.

## Local Setup

1. **Clone the repository**
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
3. **Set up Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   SECRET_KEY=your-secret-key-here
   DEBUG=True
   ALLOWED_HOSTS=127.0.0.1,localhost
   ```
4. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```
5. **Start the server**:
   ```bash
   python manage.py runserver
   ```

## Testing
Run the test suite with:
```bash
python manage.py test
```
