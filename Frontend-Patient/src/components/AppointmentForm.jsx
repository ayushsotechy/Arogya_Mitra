import axios from "axios";
import React, { useEffect, useState } from "react";
import { toast } from "react-toastify";

const AppointmentForm = () => {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [aadhar, setAadhar] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState("");
  const [appointmentDate, setAppointmentDate] = useState("");
  const [department, setDepartment] = useState("");
  const [doctorFirstName, setDoctorFirstName] = useState("");
  const [doctorLastName, setDoctorLastName] = useState("");
  const [address, setAddress] = useState("");
  const [hasVisited, setHasVisited] = useState(false);

  const [doctors, setDoctors] = useState([]);
  const [departments, setDepartments] = useState([]);

  useEffect(() => {
    const fetchDoctors = async () => {
      try {
        const { data } = await axios.get("http://localhost:4000/api/v1/user/doctors", {
          withCredentials: true,
        });

        setDoctors(data.doctors);

        // Extract unique department names dynamically
        const uniqueDepts = [...new Set(data.doctors.map(doc => doc.doctrDptmnt))];
        setDepartments(uniqueDepts);
      } catch (error) {
        console.error("Error fetching doctors:", error);
        toast.error("Failed to load doctors list");
      }
    };
    fetchDoctors();
  }, []);

  const handleAppointment = async (e) => {
    e.preventDefault();
    try {
      const { data } = await axios.post(
        "http://localhost:4000/api/v1/appointment/post",
        {
          firstName,
          lastName,
          email,
          phone,
          aadhar,
          dob,
          gender,
          appointment_date: appointmentDate,
          department,
          doctor_firstName: doctorFirstName,
          doctor_lastName: doctorLastName,
          hasVisited,
          address,
        },
        {
          withCredentials: true,
          headers: { "Content-Type": "application/json" },
        }
      );

      toast.success(data.message);
      setFirstName("");
      setLastName("");
      setEmail("");
      setPhone("");
      setAadhar("");
      setDob("");
      setGender("");
      setAppointmentDate("");
      setDepartment("");
      setDoctorFirstName("");
      setDoctorLastName("");
      setHasVisited(false);
      setAddress("");
    } catch (error) {
      toast.error(error.response?.data?.message || "Something went wrong");
    }
  };

  return (
    <div className="container form-component appointment-form">
      <h2>Appointment</h2>
      <form onSubmit={handleAppointment}>
        <div>
          <input type="text" placeholder="First Name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
          <input type="text" placeholder="Last Name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
        </div>
        <div>
          <input type="text" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          <input type="number" placeholder="Mobile" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <div>
          <input type="number" placeholder="Aadhar Number" value={aadhar} onChange={(e) => setAadhar(e.target.value)} />
          <input type="date" placeholder="Date of Birth" value={dob} onChange={(e) => setDob(e.target.value)} />
        </div>
        <div>
          <select value={gender} onChange={(e) => setGender(e.target.value)}>
            <option value="">Select Gender</option>
            <option value="Male">Male</option>
            <option value="Female">Female</option>
            <option value="Others">Others</option>
          </select>
          <input
            type="date"
            placeholder="Appointment Date"
            value={appointmentDate}
            onChange={(e) => setAppointmentDate(e.target.value)}
          />
        </div>

        <div>
          <select
            value={department}
            onChange={(e) => {
              setDepartment(e.target.value);
              setDoctorFirstName("");
              setDoctorLastName("");
            }}
          >
            <option value="">Select Department</option>
            {departments.map((dept, index) => (
              <option key={index} value={dept}>
                {dept}
              </option>
            ))}
          </select>

          <select
            value={doctorFirstName && doctorLastName ? `${doctorFirstName} ${doctorLastName}` : ""}
            onChange={(e) => {
              const [fName, lName] = e.target.value.split(" ");
              setDoctorFirstName(fName);
              setDoctorLastName(lName);
            }}
            disabled={!department}
          >
            <option value="">Select Doctor</option>
            {doctors
              .filter((doc) => doc.doctrDptmnt === department)
              .map((doc, index) => (
                <option key={index} value={`${doc.firstName} ${doc.lastName}`}>
                  {doc.firstName} {doc.lastName}
                </option>
              ))}
          </select>
        </div>

        <textarea rows="10" value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Address" />
        <div style={{ gap: "10px", justifyContent: "flex-end", flexDirection: "row" }}>
          <p>Have you visited before?</p>
          <input
            type="checkbox"
            checked={hasVisited}
            onChange={(e) => setHasVisited(e.target.checked)}
            style={{ flex: "none", width: "25px" }}
          />
        </div>

        <button type="submit">Get Appointment</button>
      </form>
    </div>
  );
};

export default AppointmentForm;
