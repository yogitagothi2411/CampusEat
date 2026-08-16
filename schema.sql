-- =====================================================================
-- CampusEats -- Database Schema (Task 5)
-- Rule followed: every table belongs to exactly ONE service.
-- Fields marked "ref only" are plain values copied from another
-- service's response -- they are NOT real foreign keys, because a
-- foreign key across services would break the service boundary.
-- =====================================================================

-- ============================
-- ACCOUNT SERVICE
-- ============================
CREATE TABLE Student (
    student_id      INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    email           VARCHAR(100) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,
    hostel_block    VARCHAR(20)
);

CREATE TABLE Address (
    address_id      INT PRIMARY KEY,
    student_id      INT NOT NULL,               -- FK inside this service
    address_line    VARCHAR(200) NOT NULL,
    block           VARCHAR(20),
    is_default      BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (student_id) REFERENCES Student(student_id)
);

-- ============================
-- CATALOGUE SERVICE
-- ============================
CREATE TABLE Restaurant (
    restaurant_id   INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    area            VARCHAR(50),
    is_active       BOOLEAN DEFAULT TRUE
);

CREATE TABLE MenuItem (
    item_id         INT PRIMARY KEY,
    restaurant_id   INT NOT NULL,               -- FK inside this service
    name            VARCHAR(100) NOT NULL,
    price           DECIMAL(8,2) NOT NULL,
    stock_quantity  INT DEFAULT 0,
    is_available    BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (restaurant_id) REFERENCES Restaurant(restaurant_id)
);

-- ============================
-- ORDER SERVICE
-- ============================
CREATE TABLE CartItem (
    cart_item_id    INT PRIMARY KEY,
    student_id      INT NOT NULL,               -- ref only (Account Service)
    item_id         INT NOT NULL,               -- ref only (Catalogue Service)
    quantity        INT NOT NULL
);

CREATE TABLE Orders (
    order_id        INT PRIMARY KEY,
    student_id      INT NOT NULL,               -- ref only (Account Service)
    address_id      INT NOT NULL,               -- ref only (Account Service)
    status          VARCHAR(20) NOT NULL,       -- PENDING, PLACED, CANCELLED...
    total_amount    DECIMAL(8,2) NOT NULL,
    payment_method  VARCHAR(20) NOT NULL,
    created_at      DATETIME NOT NULL
);

CREATE TABLE OrderItem (
    order_item_id   INT PRIMARY KEY,
    order_id        INT NOT NULL,               -- FK inside this service
    item_id         INT NOT NULL,               -- ref only (Catalogue Service)
    quantity        INT NOT NULL,
    unit_price      DECIMAL(8,2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES Orders(order_id)
);

-- ============================
-- PAYMENT SERVICE
-- ============================
CREATE TABLE Transaction (
    transaction_id  INT PRIMARY KEY,
    order_id        INT NOT NULL,               -- ref only (Order Service)
    amount          DECIMAL(8,2) NOT NULL,
    payment_method  VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,       -- SUCCESS, DECLINED...
    created_at      DATETIME NOT NULL
);

CREATE TABLE Refund (
    refund_id       INT PRIMARY KEY,
    transaction_id  INT NOT NULL,               -- FK inside this service
    amount          DECIMAL(8,2) NOT NULL,
    reason          VARCHAR(200),
    status          VARCHAR(20) NOT NULL,
    created_at      DATETIME NOT NULL,
    FOREIGN KEY (transaction_id) REFERENCES Transaction(transaction_id)
);

-- ============================
-- DELIVERY SERVICE
-- ============================
CREATE TABLE Rider (
    rider_id        INT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    phone           VARCHAR(20),
    is_available    BOOLEAN DEFAULT TRUE
);

CREATE TABLE DeliveryAssignment (
    assignment_id     INT PRIMARY KEY,
    order_id          INT NOT NULL,             -- ref only (Order Service)
    rider_id          INT NOT NULL,             -- FK inside this service
    status            VARCHAR(20) NOT NULL,     -- ASSIGNED, PICKED_UP, DELIVERED...
    current_location  VARCHAR(100),
    eta               DATETIME,
    created_at        DATETIME NOT NULL,
    FOREIGN KEY (rider_id) REFERENCES Rider(rider_id)
);

CREATE TABLE DeliveryEvent (
    event_id        INT PRIMARY KEY,
    assignment_id   INT NOT NULL,               -- FK inside this service
    event_type      VARCHAR(30) NOT NULL,
    event_time      DATETIME NOT NULL,
    FOREIGN KEY (assignment_id) REFERENCES DeliveryAssignment(assignment_id)
);

-- ============================
-- NOTIFICATION SERVICE
-- ============================
CREATE TABLE Notification (
    notification_id INT PRIMARY KEY,
    student_id      INT NOT NULL,               -- ref only (Account Service)
    order_id        INT NOT NULL,               -- ref only (Order Service)
    type            VARCHAR(30) NOT NULL,       -- ORDER_UPDATE, DELIVERY_UPDATE
    message         VARCHAR(300),
    status          VARCHAR(20) NOT NULL,       -- SENT, FAILED
    sent_at         DATETIME
);
