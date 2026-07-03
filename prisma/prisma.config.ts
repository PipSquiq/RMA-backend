import * as dotenv from "dotenv";

// Memuat berkas .env dari folder utama
dotenv.config();

export default {
  schema: "prisma/schema.prisma",
  datasource: {
    url: process.env.DATABASE_URL,
  },
};
