"""Login and authentication routes."""
from fastapi import APIRouter, Request, Depends, HTTPException, status, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from api.auth import create_access_token, verify_password, decode_access_token
from db.users import user_store
from typing import Optional

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends()
):
    """Handle login and set token in a cookie."""
    user = await user_store.get_user_by_username(form_data.username)
    if not user or not verify_password(form_data.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(
        data={"sub": user["username"], "role": user["role"]}
    )
    
    # Set the token in an HTTP-only cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=1800 * 48, # 24 hours
        samesite="lax"
    )
    
    return {"status": "success", "access_token": access_token}

@router.get("/logout")
async def logout(response: Response):
    """Log the user out by clearing the cookie."""
    response = RedirectResponse(url="/auth/login")
    response.delete_cookie("access_token")
    return response

async def get_current_user(request: Request):
    """Dependency to get the current authenticated user from cookie."""
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    
    payload = decode_access_token(token[7:])
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    
    return payload
