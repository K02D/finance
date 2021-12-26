'''Edited by Kiron Deb'''

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

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL(os.getenv("DATABASE_URL"))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")

# Store username of the user currently logged in
username = ""

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get records of current user
    rows = db.execute("SELECT Symbol, Name, Shares, Price, Total FROM purchases WHERE user_name=? ORDER BY Symbol", username)

    # Get cash balance
    cash = db.execute("SELECT cash FROM users WHERE username = ?", username)

    # Store the total assets by adding cash on hand to the value of all owned shares
    total_assets = float(cash[0]["cash"])
    for row in rows:
        total_assets += float(row["Total"])

    return render_template("portfolio.html", rows=rows, cash_on_hand=round(cash[0]["cash"], 2), total_assets = round(total_assets, 2))

@app.route("/update", methods=["GET", "POST"])
@login_required
def update():
    """Update all stock prices"""

    # Get symbols of all owned stocks
    symbols = db.execute("SELECT Symbol, Shares, Total FROM purchases WHERE user_name = ?", username)

    # Update share price and total stock value for each symbol
    for row in symbols:
        stock = lookup(row["Symbol"])
        stock_price = round(float(stock["price"]), 2)
        new_total = stock_price*row["Shares"]
        db.execute("UPDATE purchases SET Price = ?, Total = ? WHERE user_name = ? AND Symbol = ?", stock_price, new_total, username, row["Symbol"])

    return redirect("/")

@app.route("/reset")
@login_required
def reset():
    """Remove all user transactions"""

    # Delete user records from database and set cash to default value
    db.execute("DELETE FROM purchases WHERE user_name = ?", username)
    db.execute("DELETE FROM history WHERE user = ?", username)
    db.execute("UPDATE users SET cash = ? WHERE username = ?", 10000, username)

    return redirect("/")

@app.route("/add", methods=["GET","POST"])
@login_required
def add():
    """Add cash to cash balance"""

    if request.method == "GET":
        return render_template("add.html")

    else:
        # Check for invalid input
        if not request.form.get("injection") or int(request.form.get("injection")) <= 0:
            return apology("Invalid input")

        # How much cash user wishes to add
        to_add = request.form.get("injection")

        db.execute("UPDATE users SET cash = cash + ? WHERE username = ?", to_add, username)
        return redirect("/")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        # Check for invalid input
        stock = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares"))
        if not stock:
            return apology("invalid symbol, 403")
        if shares <= 0:
            return apology("invalid number of shares, 403")

        # Get stock data from lookup
        company_name = stock["name"]
        company_symbol = stock["symbol"]
        stock_price = round(float(stock["price"]), 2)

        # Get cash on hand
        retrieve_balance = db.execute("SELECT cash FROM users WHERE username=?", username)
        balance = retrieve_balance[0]["cash"]

        # Calculate total value of shares bought
        loss = round(shares*stock_price, 2)

        # Return apology if cash on hand insufficient
        if balance < loss:
            return apology("can't afford")

        # Get date and time for transaction
        datetime = strftime("%Y-%m-%d %H:%M:%S", gmtime())

        # Add record for transaction to history
        db.execute("INSERT INTO history(Date, User, Symbol, Shares, Price, [Transaction]) VALUES (?, ?, ?, ?, ?, ?)", datetime, username, company_symbol, shares, stock_price, 'Purchase')

        # Query to check if user already bought shares from this company
        owned = db.execute("SELECT Shares, Total FROM purchases WHERE Symbol=? AND user_name=?", company_symbol, username)

        # Update existing record if user already bought this company's shares
        if owned:
            total_shares = shares + int(owned[0]["Shares"])
            db.execute("UPDATE purchases SET Price = ?, Shares = ?, Total = ? WHERE Symbol = ? AND user_name = ?", stock_price, total_shares, round(total_shares*float(stock_price), 2 ), company_symbol, username)

        # Add new record if user hasn't bought this company's shares
        else:
            db.execute("INSERT INTO purchases(user_name, Symbol, Name, Shares, Price, Total) VALUES (?, ?, ?, ?, ?, ?)", username, company_symbol, company_name, shares, stock_price, loss)

        # Update cash on hand by deducting total value of shares bought
        db.execute("UPDATE users SET cash = cash - ? WHERE username = ?", loss, username)
        return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Query for user's records in history
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

        # Remember username
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
        # If stock doesn't exist return apology
        stock = lookup(request.form.get("symbol"))
        if not stock:
            return apology("invalid symbol, 403")

        # Get stock data from lookup
        company_name = stock["name"]
        company_symbol = stock["symbol"]
        stock_price = usd(stock["price"])

        # Format output string
        output = f'{company_name} ({company_symbol}) stock price: {stock_price}'

        return render_template("quoted.html", message=output)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:

        # If no username entered
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # If password not entered twice
        if not request.form.get("password") or not request.form.get("confirmation"):
            return apology("must provide password twice", 403)

        # If passwords don't match
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 403)

        # If username exists in database
        rows = db.execute("SELECT username FROM users WHERE username = ?", request.form.get("username"))
        if rows:
            return apology("username taken", 403)

        # Generate password hash
        pass_hash = generate_password_hash(request.form.get("password"))

        # Add user record to users table in database
        db.execute("INSERT INTO users(username, hash) VALUES(?, ?)", request.form.get("username"), pass_hash)

    return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get symbols and counts of shares owned
    shares_owned = db.execute("SELECT Symbol, Shares FROM purchases WHERE user_name = ?", username)

    if request.method == "GET":
        # Displays a dropdown containing symbols of all owned shares
        return render_template("sell.html", owned = shares_owned)

    else:
        # Check for invalid input
        if not request.form.get("shares") or int(request.form.get("shares")) <= 0:
            return apology("Must sell 1 or more shares", 403)
        if not request.form.get("symbol"):
            return apology("No symbol selected", 403)

        # Get user input
        num_to_sell = int(request.form.get("shares"))
        symb = request.form.get("symbol")

        # Check for erroneous input
        if not num_to_sell or num_to_sell <= 0:
            return apology("Must sell 1 or more shares", 403)
        if not symb:
            return apology("No symbol selected", 403)

        # Get stock data from lookup
        stock = lookup(symb)
        company_name = stock["name"]
        company_symbol = stock["symbol"]
        stock_price = stock["price"]

        # Get number of shares already owned
        no_owned = db.execute("SELECT Shares FROM purchases WHERE user_name = ? AND Symbol = ?", username, company_symbol)

        # Apologies for invalid input
        if num_to_sell <= 0:
            return apology("Must sell 1 or more shares!", 403)
        elif int(no_owned[0]["Shares"]) < num_to_sell:
            return apology("You don't own that many shares of the company!", 403)

        # If selling all owned shares then delete record
        if int(no_owned[0]["Shares"]) == num_to_sell:
            db.execute("DELETE FROM purchases WHERE symbol = ? AND user_name = ?", company_symbol, username)

        else:
            # Update total value of shares owned
            new_total = (int(no_owned[0]["Shares"]) - num_to_sell)*float(stock_price)

            # Update number of shares owned, current share price and total value of shares owned
            db.execute("UPDATE purchases SET Shares = Shares - ?, Price = ?, Total = ? WHERE Symbol = ? AND user_name = ?", num_to_sell, stock_price, new_total, company_symbol, username)

        # Update cash by adding value of shares sold
        gain = float(stock_price)*num_to_sell
        db.execute("UPDATE users SET cash = cash + ? WHERE username = ?", gain, username)

        # Format date and time for ouput
        datetime = strftime("%Y-%m-%d %H:%M:%S", gmtime())

        # Add record for transaction to history
        db.execute("INSERT INTO history(Date, User, Symbol, Shares, Price, [Transaction]) VALUES (?, ?, ?, ?, ?, ?)", datetime, username, company_symbol, num_to_sell, stock_price, 'Sale')

        # Redirect to home page to display portfolio
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)