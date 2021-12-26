import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from time import gmtime, strftime
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

#stores the username of the user currently logged in
username = ""

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    # get recor
    rows = db.execute("SELECT Symbol, Name, Shares, Price, Total FROM purchases WHERE user_name=?", username)
    cash = db.execute("SELECT cash FROM users WHERE username = ?", username)

    total = float(cash[0]["cash"])
    for row in rows:
        total += float(row["Total"])
    return render_template("portfolio.html", rows=rows, balance=usd(cash[0]["cash"]), total = round(total, 2))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")

    stock = lookup(request.form.get("symbol"))
    shares = int(request.form.get("shares")) # number of shares bought

    if not stock:
        return apology("invalid symbol, 403")
    if shares <= 0:
        return apology("invalid number of shares, 403")

    company_name = stock["name"]
    company_symbol = stock["symbol"]
    stock_price = str(round(float(stock["price"]), 2))
    retrieve_balance = db.execute("SELECT cash FROM users WHERE username=?", username)
    balance = retrieve_balance[0]["cash"]
    total = round(shares*float(stock_price), 2)

    if balance < total:
        return apology("can't afford, 403")

    datetime = strftime("%Y-%m-%d %H:%M:%S", gmtime())
    db.execute("INSERT INTO history(Date, User, Symbol, Shares, Price, [Transaction]) VALUES (?, ?, ?, ?, ?, ?)", datetime, username, company_symbol, shares, stock_price, 'Purchase')
 
    loss = shares*float(stock_price)
    temp = db.execute("SELECT Shares, Total FROM purchases WHERE Symbol=? AND user_name=?", company_symbol, username)
    
    if temp:   # if user has already bought this company's shares
        total_shares = shares + int(temp[0]["Shares"])
        db.execute("UPDATE purchases SET Price = ?, Shares = ?, Total = ? WHERE Symbol = ? AND user_name = ?", stock_price, total_shares, str(round(total_shares*float(stock_price), 2 )), company_symbol, username)
    else:
        db.execute("INSERT INTO purchases(user_name, Symbol, Name, Shares, Price, Total) VALUES (?, ?, ?, ?, ?, ?)", username, company_symbol, company_name, shares, stock_price, total)

    db.execute("UPDATE users SET cash = cash - ? WHERE username = ?", loss, username)
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    hist_data = db.execute("SELECT Symbol, Shares, Price, Date, [Transaction] FROM history WHERE user=? ORDER BY Date DESC", username)
    return render_template("history.html", data = hist_data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        global username
        username = request.form.get("username")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("invalid symbol, 403")
        company_name = stock["name"]
        company_symbol = stock["symbol"]
        stock_price = usd(stock["price"])
        output = f'{company_name} ({company_symbol}) stock price: {stock_price}'
        return render_template("quoted.html", message=output)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        if not request.form.get("username"):
            return apology("must provide username", 403)

        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password twice", 403)

        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 403)

        rows = db.execute("SELECT username FROM users WHERE username = :username",
                          username=request.form.get("username"))
        if rows:
            return apology("username taken", 403)

        pass_hash = generate_password_hash(request.form.get("password"))
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", request.form.get("username"), pass_hash)


    return render_template("index.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    shares_owned = db.execute("SELECT Symbol, Shares FROM purchases WHERE user_name = ?", username)

    if request.method == "GET":
        return render_template("sell.html", owned = shares_owned)
    else:
        num_to_sell = int(request.form.get("shares"))
        symb = request.form.get("symbol")
        
        stock = lookup(symb)
        company_name = stock["name"]
        company_symbol = stock["symbol"]
        stock_price = stock["price"]
        no_owned = db.execute("SELECT Shares FROM purchases WHERE user_name = ? AND Symbol = ?", username, company_symbol)
       
        if num_to_sell <= 0:
            return apology("Must sell 1 or more shares!", 403)
        if int(no_owned[0]["Shares"]) < num_to_sell:
            return apology("You don't own that many shares of the company!", 403)
        
        if int(no_owned[0]["Shares"]) == num_to_sell:
            db.execute("DELETE FROM purchases WHERE symbol = ? AND user_name = ?", company_symbol, username)
        else:
            new_total = (int(no_owned[0]["Shares"]) - num_to_sell)*float(stock_price)
            db.execute("UPDATE purchases SET Shares = Shares - ?, Price = ?, Total = ? WHERE Symbol = ? AND user_name = ?", num_to_sell, stock_price, new_total, company_symbol, username)
        
        gain = float(stock_price)*num_to_sell
        db.execute("UPDATE users SET cash = cash + ? WHERE username = ?", gain, username)
        
        datetime = strftime("%Y-%m-%d %H:%M:%S", gmtime())
        db.execute("INSERT INTO history(Date, User, Symbol, Shares, Price, [Transaction]) VALUES (?, ?, ?, ?, ?, ?)", datetime, username, company_symbol, num_to_sell, stock_price, 'Sale')
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
