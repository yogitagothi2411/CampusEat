CREATE DATABASE IF NOT EXISTS campuseats;
USE campuseats;

CREATE TABLE IF NOT EXISTS dishes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  available BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO dishes (name, price, available) VALUES
('Veg Sandwich', 60.00, TRUE),
('Masala Dosa', 80.00, TRUE),
('Chole Kulche', 75.00, TRUE),
('Cold Coffee', 50.00, TRUE);
