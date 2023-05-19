package org.crazybunqnq.svn2git;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@EnableScheduling
@SpringBootApplication
public class Svn2GitApplication {

    public static void main(String[] args) {
        SpringApplication.run(Svn2GitApplication.class, args);
    }
}
