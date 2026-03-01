import numpy as np  # For numerical operations and array handling
import tensorflow as tf  # TensorFlow for loading and using deep learning models
from keras.preprocessing import image  # For image preprocessing
import os  # For file system interactions (not used in this snippet)

# Load pre-trained models for fracture detection and body part classification
model_elbow_frac = tf.keras.models.load_model("fracture_models/ResNet50_Elbow_frac_best.h5")  # Elbow fracture model
model_hand_frac = tf.keras.models.load_model("fracture_models/ResNet50_Hand_frac_best.h5")  # Hand/Wrist fracture model
model_shoulder_frac = tf.keras.models.load_model("fracture_models/ResNet50_Shoulder_frac_best.h5")  # Shoulder fracture model
model_parts = tf.keras.models.load_model("fracture_models/ResNet50_BodyParts.h5")  # Body part classification model

# Define class labels for body part and fracture status predictions
categories_parts = ["elbow", "wrist", "shoulder"]  # Possible body parts
categories_fracture = ["fractured", "normal"]  # Possible fracture status labels

# Function to predict whether a bone in an image is fractured and identify the body part
def predict_fracture(image_path):
    size = 224  # Target input size for the model
    temp_img = image.load_img(image_path, target_size=(size, size))  # Load and resize the image
    x = image.img_to_array(temp_img)  # Convert image to array
    x = np.expand_dims(x, axis=0)  # Add batch dimension
    images = np.vstack([x])  # Stack image into a batch (1 image here)

    # Predict the body part using the body part classification model
    part_idx = np.argmax(model_parts.predict(images), axis=1).item()  # Get predicted class index
    body_part = categories_parts[part_idx]  # Get body part label

    # Select the corresponding fracture detection model based on predicted body part
    if body_part == "wrist":
        part_model = model_hand_frac  # Use hand/wrist model
        model_name = "Hand"
    elif body_part == "elbow":
        part_model = model_elbow_frac  # Use elbow model
        model_name = "Elbow"
    elif body_part == "shoulder":
        part_model = model_shoulder_frac  # Use shoulder model
        model_name = "Shoulder"

    # Predict whether the identified body part is fractured or normal
    frac_idx = np.argmax(part_model.predict(images), axis=1).item()  # Get predicted class index
    fracture_status = categories_fracture[frac_idx]  # Get fracture status label

    # Return result based on fracture status
    if fracture_status == "fractured":
        return f"Fracture detected on {model_name}"  # Fracture found
    else:
        return f"No fracture detected on {model_name}"  # No fracture found
