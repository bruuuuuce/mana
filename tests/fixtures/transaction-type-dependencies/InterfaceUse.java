package fixture;
import org.springframework.stereotype.Service;
@Service class Entry implements MissingInterface {
    public void run() { inheritedDefault(); }
}
