from flask import Flask, request, render_template, redirect, url_for, flash
import pandas as pd
from pymongo import MongoClient
import bcrypt
import os
from werkzeug.utils import secure_filename
import tensorflow as tf
import numpy as np
from PIL import Image
from statsmodels.tsa.statespace.sarimax import SARIMAX

# Flask setup
app = Flask(__name__)
app.secret_key = 'd4a92bb4544a18d31a7a908284a2a357'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['user_database']
users_collection = db['users']

# Load vegetable price dataset
def load_data():
    data = pd.read_csv('vegetables_prices_additional_data.csv')
    data['Date'] = pd.to_datetime(data['Date'])
    data.sort_values(by='Date', inplace=True)
    return data

data = load_data()

# Price forecasting logic
def forecast_prices(state, district, market, vegetable, start_date):
    filtered_data = data[
        (data['State'] == state) &
        (data['District'] == district) &
        (data['Market'] == market) &
        (data['Vegetable'] == vegetable)
    ]
    
    if filtered_data.empty:
        return None, None

    filtered_data.set_index('Date', inplace=True)
    target = filtered_data['Modal_Price']

    model = SARIMAX(target, order=(1, 1, 1), seasonal_order=(1, 1, 1, 7))
    result = model.fit(disp=False)

    forecast_dates = pd.date_range(start=pd.to_datetime(start_date), periods=15)
    forecast = result.get_forecast(steps=15)
    forecast_values = forecast.predicted_mean

    return forecast_dates, forecast_values

# Load soil model once
soil_model = tf.keras.models.load_model("soil_classifier_model.h5")
CLASS_NAMES = ['Alluvial soil', 'Clayey soils', 'Laterite soil', 'Loamy soil', 'Sandy loam', 'Sandy soil']

# Predict soil type from image
def predict_soil_type(image_path):
    img = Image.open(image_path).convert('RGB')
    img = img.resize((224, 224))
    img_array = tf.keras.preprocessing.image.img_to_array(img)
    img_array = tf.expand_dims(img_array, 0)
    img_array = img_array / 255.0
    predictions = soil_model.predict(img_array)
    predicted_class = CLASS_NAMES[np.argmax(predictions[0])]
    return predicted_class

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    email = request.form.get('signupEmail')
    password = request.form.get('signupPassword')
    confirm_password = request.form.get('signupConfirmPassword')

    if password != confirm_password:
        flash("Passwords do not match!")
        return redirect(url_for('home'))

    if users_collection.find_one({'email': email}):
        flash("Email is already registered!")
        return redirect(url_for('home'))

    hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    users_collection.insert_one({'email': email, 'password': hashed_password})
    flash("Sign up successful! You can now log in.")
    return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form.get('loginEmail')
    password = request.form.get('loginPassword')

    user = users_collection.find_one({'email': email})
    if user and bcrypt.checkpw(password.encode('utf-8'), user['password']):
        flash("Login successful!")
        return redirect(url_for('home'))
    else:
        flash("Invalid email or password!")
        return redirect(url_for('home'))

@app.route('/predict', methods=['GET'])
def show_predict_page():
    return render_template('predict.html', forecast_data=None)

@app.route('/predict', methods=['POST'])
def predict():
    state = request.form.get('state')
    district = request.form.get('district')
    market = request.form.get('market')
    vegetable = request.form.get('vegetable')
    start_date = request.form.get('start_date')

    forecast_dates, forecast_values = forecast_prices(state, district, market, vegetable, start_date)

    if forecast_dates is None or forecast_values is None:
        return render_template('predict.html', error="No data available for the given inputs.", forecast_data=None)

    forecast_data = [
        {'date': str(date.date()), 'predicted_price': round(price, 2)}
        for date, price in zip(forecast_dates, forecast_values)
    ]

    return render_template('predict.html', forecast_data=forecast_data, error=None)

# Soil Prediction Route
@app.route('/templates/service2.html', methods=['GET', 'POST'])
def service2():
    predicted_soil = None
    soil_info = None
    image_url = None

    if request.method == 'POST':
        if 'soilImage' not in request.files:
            return render_template('service2.html', prediction="No file uploaded.")

        file = request.files['soilImage']
        if file.filename == '':
            return render_template('service2.html', prediction="No file selected.")

        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        predicted_soil = predict_soil_type(filepath)
        image_url = f'/static/uploads/{filename}'  # for displaying the uploaded image

        characteristics = {
    'Alluvial soil': [
        "1. Rich in nutrients, ideal for agriculture.",
        "2. Found in river valleys and deltas, especially near rivers and lakes.",
        "3. Fertile and easy to work with, supports high crop yields.",
        "4. Well-drained, ensuring optimal plant growth.",
        "5. Commonly used for growing rice, wheat, and other crops.",
        "6. Soil texture varies but is usually a mix of sand, silt, and clay."
    ],
    
    'Clayey soils': [
        "1. High water retention, which may lead to poor drainage.",
        "2. Sticky when wet and hard when dry, making it difficult to work with.",
        "3. Rich in nutrients but may be prone to waterlogging.",
        "4. Typically found in low-lying areas and riverbanks.",
        "5. Often requires good soil management to avoid compaction.",
        "6. Best suited for crops that thrive in moisture-rich environments."
    ],
    
    'Laterite soil': [
        "1. Rich in iron and aluminum, giving it a reddish or yellowish color.",
        "2. Highly acidic, which may limit its suitability for some plants.",
        "3. Found in tropical regions with heavy rainfall and high temperatures.",
        "4. Poor in nutrients, so fertilization is often needed for agricultural use.",
        "5. Soil can become hard and compact, requiring deep plowing to improve aeration.",
        "6. Often used for building materials in tropical regions due to its hardening properties."
    ],
    
    'Loamy soil': [
        "1. Considered the ideal soil type for most plant growth.",
        "2. A perfect balance of sand, silt, and clay, providing good aeration.",
        "3. Retains enough moisture while allowing excess water to drain, preventing root rot.",
        "4. Rich in nutrients, supporting healthy plant development.",
        "5. Easy to work with, allowing for deep root growth.",
        "6. Ideal for growing a wide variety of plants, including vegetables, fruits, and flowers."
    ],
    
    'Sandy loam': [
        "1. Good drainage, preventing waterlogging of roots.",
        "2. Moderate water retention, suitable for most plants.",
        "3. Easy to work with, often requiring less effort for tilling and planting.",
        "4. Holds enough nutrients to support healthy plant growth.",
        "5. Well-suited for crops like vegetables, flowers, and shrubs.",
        "6. May require organic matter addition to improve fertility over time."
    ],
    
    'Sandy soil': [
        "1. Large particles, resulting in excellent drainage.",
        "2. Low nutrient content, requiring regular fertilization for optimal plant growth.",
        "3. Poor water retention, so frequent watering is needed for plants.",
        "4. Light and easy to work with, ideal for crops like melons and root vegetables.",
        "5. Often prone to erosion due to its loose texture and lack of cohesion.",
        "6. Can be amended with organic matter to improve nutrient and moisture retention."
    ]
}

        soil_info = characteristics.get(predicted_soil, "No information available.")

    return render_template('service2.html', prediction=predicted_soil, soil_info=soil_info, image_url=image_url)

# Run app
if __name__ == '__main__':
    app.run(debug=True)
