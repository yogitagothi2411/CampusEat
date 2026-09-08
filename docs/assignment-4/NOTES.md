# CS543 – Web Services – Assignment 4

## Rebuilding CampusEats Orders Service in REST

### Team Members

| Roll No     | Name             |
|-------------|------------------|
| 20251651107 | Yogita Gothi     |
| 20251651047 | Janvi Goud       |
| 20251651086 | Shreya Verma     |
| 20251651088 | Sonali Choudhary |

---

# Part A – Model the Service

## A2. SOAP Operations from Assignment 3

The main operations identified from the previous CampusEats design are:

* `addToCart(studentId, itemId, quantity)`
* `placeOrder(studentId, items, addressId, paymentMethod)`
* `getOrder(studentId, orderId)`
* `cancelOrder(studentId, orderId)`

For Assignment 4, these operations were redesigned as REST resources rather than action-oriented SOAP operations.

---

## A4. REST Resource Table

| Method | URL                                             | What it does                                       | Success Code | Failure Codes      |
| ------ | ----------------------------------------------- | -------------------------------------------------- | ------------ | ------------------ |
| POST   | `/orders`                                       | Creates a new order                                | 201 Created  | 400, 409, 422, 503 |
| GET    | `/orders/{orderId}`                             | Retrieves one order                                | 200 OK       | 404                |
| GET    | `/orders?studentId={studentId}&status={status}` | Retrieves orders filtered by student and/or status | 200 OK       | 400                |
| POST   | `/orders/{orderId}/cancellation`                | Changes an existing order to the cancelled state   | 200 OK       | 404, 409, 422      |

The REST API uses `/orders` as the main resource because an order is a durable business entity owned by the Orders Service.

---

## A5. Difficult Resource Mapping

The operation that mapped least comfortably to REST was `cancelOrder()`. In the SOAP design, cancellation was represented directly as an operation, but in REST an order should remain a resource after cancellation because its history and status are still important. Therefore, `POST /orders/{orderId}/cancellation` was chosen as a state-changing sub-resource. `DELETE /orders/{orderId}` was rejected because cancellation should not physically delete the order from the system.

---

# Part D – Dependency and Fallback

## D1/D2. Outbound Payment Service Call

The Orders Service makes an HTTP call to the Payments Service when an order requires payment processing.

The Payments Service URL is obtained from the environment variable:

`PAYMENTS_URL`

The URL is not hard-coded in the application.

The outbound request uses a timeout and retries transient network failures using exponential backoff and jitter.

HTTP 4xx responses are not retried because they represent client or business errors rather than temporary network failures.

When a create/payment request is retried, an idempotency key is included so that the same operation cannot create a duplicate payment.

---

## D3. Fallback

If the Payments Service remains unavailable after the configured retries, the Orders Service fails safely instead of pretending that the order was successfully placed. The service returns an appropriate `503 Service Unavailable` response. Degrading the operation would be unsafe because the order should not be reported as successfully placed when payment has not been confirmed.

---

# Question 1 – WSDL vs OpenAPI

The Assignment 3 WSDL contains [X] lines.

The Assignment 4 `openapi.yaml` contains [Y] lines.

Therefore, the difference is:

`[X] - [Y] = [difference] lines`

The difference is not simply the amount of information in the two files. The WSDL contains SOAP-specific information that is unnecessary in the REST/OpenAPI contract.

Two examples are:

1. SOAP binding information such as the SOAP binding and SOAP operation details.
2. SOAP message/envelope and SOAP-specific transport/binding information.

OpenAPI instead describes HTTP methods, URLs, parameters, request bodies, responses and reusable schemas.

---

# Question 2 – SOAP Fault vs REST Error

One SOAP fault from the previous assignment was:

```xml
<faultcode>soapenv:Client</faultcode>
<faultstring>Payment declined by issuing bank</faultstring>
```

In the REST implementation this is represented using an HTTP error status and the common problem format:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/json
```

```json
{
  "type": "https://campuseats/errors/payment-declined",
  "title": "Payment declined",
  "status": 422,
  "detail": "The issuing bank declined the transaction."
}
```

Returning the error inside a `200 OK` response is a problem because HTTP infrastructure interprets the response as successful. Clients, proxies, monitoring systems and other intermediaries may therefore treat the failed business operation as a successful request. Using the correct HTTP status code allows the failure to be understood by the network and the client without having to inspect the application response body.

---

# Question 3 – UDDI Publish, Find and Bind

The three UDDI activities were publish, find and bind.

In the REST setup, the idea of publishing still exists through the OpenAPI contract and service deployment/documentation. Finding the service is handled through the service's configured address or service discovery mechanism rather than the old UDDI registry. Binding is replaced by making an HTTP request to the REST endpoint.

OpenAPI takes over much of the contract-description role that WSDL and UDDI-related documentation previously provided, while HTTP provides the standard mechanism for invoking the service.

---

# Question 4 – XML Schema vs REST Validation

The specific function in our code that performs request validation is:

`validate()`

The XML Schema in the SOAP implementation automatically checked the structure and required fields of incoming messages before the application logic processed them. In the REST implementation, this responsibility is explicitly handled by `validate()`.

For example, without `validate()`, a request such as:

```json
{
  "studentId": "STU-001",
  "items": []
}
```

could reach the order-creation logic even though an order must contain at least one item. This could result in an invalid order or an application error.

---

# Question 5 – When Would SOAP Still Be Preferred?

I would still choose SOAP when integrating with an enterprise system that specifically requires WS-* standards. For example, WS-Security can provide standardized message-level security mechanisms that are different from simply protecting an HTTP connection with HTTPS.

The guarantee being purchased is standardized message-level security and the associated SOAP/WS-* processing model. If that specific enterprise requirement did not exist, REST would generally be simpler for this CampusEats service.
